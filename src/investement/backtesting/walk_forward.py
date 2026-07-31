from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite, sqrt
from statistics import mean, median

from investement.domain import PriceBar, SignalAction, require_aware


@dataclass(frozen=True)
class RecommendationObservation:
    symbol: str
    as_of: datetime
    action: SignalAction
    score: float
    confidence: float
    observed_price: float
    fair_value: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("recommendation symbol is required")
        require_aware(self.as_of, "as_of")
        for value, name in (
            (self.score, "score"),
            (self.confidence, "confidence"),
            (self.observed_price, "observed_price"),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not -1 <= self.score <= 1 or not 0 <= self.confidence <= 1:
            raise ValueError("score and confidence are outside their valid ranges")
        if self.observed_price <= 0:
            raise ValueError("observed_price must be positive")
        if self.fair_value is not None and (
            not isfinite(self.fair_value) or self.fair_value <= 0
        ):
            raise ValueError("fair_value must be positive and finite")


@dataclass(frozen=True)
class ForwardOutcome:
    recommendation: RecommendationObservation
    entry_at: datetime
    evaluation_at: datetime
    entry_price: float
    evaluation_price: float
    underlying_total_return: float
    directional_return: float
    directional_profit_loss_per_share: float
    correct_direction: bool | None
    transaction_cost_rate: float = 0.0


@dataclass(frozen=True)
class WalkForwardMetrics:
    recommendations: int
    actionable: int
    buys: int
    reductions_or_sells: int
    holds: int
    hit_rate: float | None
    mean_directional_return: float | None
    median_directional_return: float | None
    mean_buy_return: float | None
    mean_monthly_rank_ic: float | None
    positive_months: float | None


def evaluate_recommendations(
    recommendations: Sequence[RecommendationObservation],
    bars_by_symbol: Mapping[str, Sequence[PriceBar]],
    evaluation_at: datetime,
    *,
    signal_delay_bars: int = 1,
    transaction_cost_bps: float = 0.0,
) -> tuple[ForwardOutcome, ...]:
    """Evaluate signals causally using the first complete bar after the cutoff."""
    require_aware(evaluation_at, "evaluation_at")
    if signal_delay_bars < 1:
        raise ValueError("signal_delay_bars must be at least one")
    if transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps cannot be negative")
    cost_rate = transaction_cost_bps / 10_000.0
    outcomes = []
    for recommendation in recommendations:
        if evaluation_at <= recommendation.as_of:
            raise ValueError("evaluation_at must be after every recommendation cutoff")
        bars = tuple(
            sorted(
                (
                    bar
                    for bar in bars_by_symbol.get(recommendation.symbol, ())
                    if bar.provenance.available_at <= evaluation_at
                ),
                key=lambda item: item.timestamp,
            )
        )
        candidates = tuple(
            bar for bar in bars if bar.provenance.available_at > recommendation.as_of
        )
        if len(candidates) < signal_delay_bars:
            continue
        entry = candidates[signal_delay_bars - 1]
        exits = tuple(bar for bar in bars if bar.timestamp >= entry.timestamp)
        if not exits:
            continue
        final = exits[-1]
        total_return = final.adjusted_close / entry.adjusted_close - 1
        direction = _direction(recommendation.action)
        directional_return = direction * total_return
        if direction:
            directional_return -= cost_rate
        outcomes.append(
            ForwardOutcome(
                recommendation=recommendation,
                entry_at=entry.provenance.available_at,
                evaluation_at=final.provenance.available_at,
                entry_price=entry.close,
                evaluation_price=final.close,
                underlying_total_return=total_return,
                directional_return=directional_return,
                directional_profit_loss_per_share=entry.close * directional_return,
                correct_direction=(directional_return > 0 if direction else None),
                transaction_cost_rate=cost_rate,
            )
        )
    return tuple(outcomes)


def apply_cost_stress(
    outcomes: Sequence[ForwardOutcome], transaction_cost_bps: float
) -> tuple[ForwardOutcome, ...]:
    if transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps cannot be negative")
    rate = transaction_cost_bps / 10_000.0
    stressed = []
    for item in outcomes:
        direction = _direction(item.recommendation.action)
        directional = direction * item.underlying_total_return - (rate if direction else 0.0)
        stressed.append(
            replace(
                item,
                directional_return=directional,
                directional_profit_loss_per_share=item.entry_price * directional,
                correct_direction=(directional > 0 if direction else None),
                transaction_cost_rate=rate,
            )
        )
    return tuple(stressed)


def summarize_walk_forward(outcomes: Sequence[ForwardOutcome]) -> WalkForwardMetrics:
    actionable = tuple(
        item for item in outcomes if _direction(item.recommendation.action) != 0
    )
    buys = tuple(
        item for item in outcomes if item.recommendation.action is SignalAction.BUY
    )
    monthly = defaultdict(list)
    for item in actionable:
        monthly[item.recommendation.as_of].append(item)
    monthly_directional = [mean(item.directional_return for item in values) for values in monthly.values()]
    monthly_ics = [
        value
        for values in monthly.values()
        if (value := _rank_ic(values)) is not None
    ]
    return WalkForwardMetrics(
        recommendations=len(outcomes),
        actionable=len(actionable),
        buys=len(buys),
        reductions_or_sells=sum(
            item.recommendation.action in (SignalAction.REDUCE, SignalAction.SELL)
            for item in outcomes
        ),
        holds=sum(item.recommendation.action is SignalAction.HOLD for item in outcomes),
        hit_rate=(
            mean(bool(item.correct_direction) for item in actionable) if actionable else None
        ),
        mean_directional_return=(
            mean(item.directional_return for item in actionable) if actionable else None
        ),
        median_directional_return=(
            median(item.directional_return for item in actionable) if actionable else None
        ),
        mean_buy_return=(mean(item.underlying_total_return for item in buys) if buys else None),
        mean_monthly_rank_ic=(mean(monthly_ics) if monthly_ics else None),
        positive_months=(
            mean(value > 0 for value in monthly_directional) if monthly_directional else None
        ),
    )


def _direction(action: SignalAction) -> int:
    if action is SignalAction.BUY:
        return 1
    if action in (SignalAction.REDUCE, SignalAction.SELL):
        return -1
    return 0


def _rank_ic(outcomes: Sequence[ForwardOutcome]) -> float | None:
    if len(outcomes) < 3:
        return None
    scores = tuple(item.recommendation.score for item in outcomes)
    returns = tuple(item.underlying_total_return for item in outcomes)
    score_ranks = _ranks(scores)
    return_ranks = _ranks(returns)
    score_mean = mean(score_ranks)
    return_mean = mean(return_ranks)
    covariance = sum(
        (left - score_mean) * (right - return_mean)
        for left, right in zip(score_ranks, return_ranks)
    )
    left_variance = sum((value - score_mean) ** 2 for value in score_ranks)
    right_variance = sum((value - return_mean) ** 2 for value in return_ranks)
    denominator = sqrt(left_variance * right_variance)
    return covariance / denominator if denominator > 0 else None


def _ranks(values: Sequence[float]) -> tuple[float, ...]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for index, _ in indexed[cursor:end]:
            result[index] = rank
        cursor = end
    return tuple(result)
