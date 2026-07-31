"""Causal monthly comparison of constrained portfolio allocation models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import ceil, isfinite, sqrt, tanh
from statistics import mean, stdev

from investement.portfolio.constraints import project_weights
from investement.portfolio.models import AssetMetadata, PortfolioConstraints

MODEL_NAMES = (
    "equal_weight",
    "inverse_volatility",
    "minimum_variance",
    "mean_variance",
    "risk_parity",
    "hierarchical_risk_parity",
    "black_litterman_proxy",
    "cvar_risk_budget",
    "turnover_aware",
)


@dataclass(frozen=True)
class ModelEvaluation:
    model: str
    validation_return: float
    validation_annualized_return: float
    validation_volatility: float
    validation_max_drawdown: float
    validation_expected_shortfall: float
    turnover: float
    score: float
    effective_assets: float


@dataclass(frozen=True)
class TournamentDecision:
    selected_model: str
    selected_weights: Mapping[str, float]
    evaluations: Sequence[ModelEvaluation]


def select_monthly_model(
    estimation_returns: Mapping[str, Sequence[float]],
    validation_returns: Mapping[str, Sequence[float]],
    live_returns: Mapping[str, Sequence[float]],
    constraints: PortfolioConstraints,
    metadata: Mapping[str, AssetMetadata],
    previous_weights: Mapping[str, float] | None = None,
    transaction_cost_bps: float = 5.0,
) -> TournamentDecision:
    """Select a model using a prior validation window, then refit its weights.

    ``estimation_returns`` end before ``validation_returns``. The selected model
    is therefore evaluated only on information that was available before the
    rebalance. ``live_returns`` is used only to refit the selected model for the
    next holding period.
    """

    _validate_windows(estimation_returns, validation_returns, live_returns)
    candidates = build_candidate_weights(
        estimation_returns,
        constraints,
        metadata,
        previous_weights=previous_weights,
    )
    evaluations = tuple(
        _evaluate_model(
            model,
            weights,
            validation_returns,
            previous_weights or {},
            transaction_cost_bps,
        )
        for model, weights in candidates.items()
    )
    winner = max(evaluations, key=lambda item: (item.score, -MODEL_NAMES.index(item.model)))
    live_candidates = build_candidate_weights(
        live_returns,
        constraints,
        metadata,
        previous_weights=previous_weights,
    )
    return TournamentDecision(
        selected_model=winner.model,
        selected_weights=dict(live_candidates[winner.model]),
        evaluations=evaluations,
    )


def build_candidate_weights(
    returns: Mapping[str, Sequence[float]],
    constraints: PortfolioConstraints,
    metadata: Mapping[str, AssetMetadata],
    previous_weights: Mapping[str, float] | None = None,
) -> Mapping[str, Mapping[str, float]]:
    """Build all candidate portfolios with the same hard constraints."""

    _validate_returns(returns)
    scores = _asset_statistics(returns)
    candidates = {
        "equal_weight": _project({asset: 1.0 for asset in returns}, constraints, metadata),
        "inverse_volatility": _project(
            {asset: 1.0 / max(values["volatility"], 1e-12) for asset, values in scores.items()},
            constraints,
            metadata,
        ),
        "minimum_variance": _minimum_variance(returns, constraints, metadata),
        "mean_variance": _project(
            {
                asset: max(values["mean"], 0.0) / max(values["volatility"], 1e-12)
                for asset, values in scores.items()
            },
            constraints,
            metadata,
        ),
        "risk_parity": _risk_parity(returns, constraints, metadata),
        "hierarchical_risk_parity": _hierarchical_risk_parity(returns, constraints, metadata),
        "black_litterman_proxy": _black_litterman_proxy(returns, constraints, metadata),
        "cvar_risk_budget": _project(
            {asset: 1.0 / max(values["expected_shortfall"], 1e-4) for asset, values in scores.items()},
            constraints,
            metadata,
        ),
    }
    if previous_weights:
        base = candidates["inverse_volatility"]
        blended = {
            asset: 0.60 * float(previous_weights.get(asset, 0.0))
            + 0.40 * float(base.get(asset, 0.0))
            for asset in returns
        }
        candidates["turnover_aware"] = _project(blended, constraints, metadata)
    else:
        candidates["turnover_aware"] = candidates["inverse_volatility"]
    return candidates


def _evaluate_model(
    model: str,
    weights: Mapping[str, float],
    returns: Mapping[str, Sequence[float]],
    previous_weights: Mapping[str, float],
    transaction_cost_bps: float,
) -> ModelEvaluation:
    portfolio_returns = tuple(
        sum(float(weights[asset]) * float(returns[asset][index]) for asset in weights)
        for index in range(len(next(iter(returns.values()))))
    )
    turnover = _turnover(weights, previous_weights)
    if transaction_cost_bps:
        portfolio_returns = list(portfolio_returns)
        portfolio_returns[0] -= turnover * transaction_cost_bps / 10_000.0
        portfolio_returns = tuple(portfolio_returns)
    wealth = [1.0]
    for value in portfolio_returns:
        wealth.append(wealth[-1] * (1.0 + value))
    total_return = wealth[-1] - 1.0
    years = max(len(portfolio_returns) / 252.0, 1 / 252.0)
    annualized_return = (1.0 + total_return) ** (1.0 / years) - 1.0
    volatility = _stdev(portfolio_returns) * sqrt(252.0)
    maximum_drawdown = _max_drawdown(wealth)
    expected_shortfall = _expected_shortfall(portfolio_returns)
    score = (
        annualized_return
        - 0.40 * volatility
        - 0.30 * abs(maximum_drawdown)
        - 0.15 * expected_shortfall * sqrt(252.0)
        - 0.05 * turnover
    )
    return ModelEvaluation(
        model=model,
        validation_return=total_return,
        validation_annualized_return=annualized_return,
        validation_volatility=volatility,
        validation_max_drawdown=maximum_drawdown,
        validation_expected_shortfall=expected_shortfall,
        turnover=turnover,
        score=score,
        effective_assets=_effective_assets(weights),
    )


def _minimum_variance(returns, constraints, metadata):
    assets = tuple(returns)
    covariance = _covariance(returns)
    weights = {asset: 1.0 / len(assets) for asset in assets}
    for _ in range(200):
        marginal = {
            asset: sum(covariance[asset][other] * weights[other] for other in assets)
            for asset in assets
        }
        positive = [value for value in marginal.values() if value > 1e-12]
        target = mean(positive) if positive else 1.0
        updated = {
            asset: weights[asset] * target / max(marginal[asset], 1e-12) for asset in assets
        }
        total = sum(updated.values())
        if total <= 0:
            break
        updated = {asset: value / total for asset, value in updated.items()}
        if max(abs(updated[asset] - weights[asset]) for asset in assets) < 1e-8:
            break
        weights = updated
    return _project(weights, constraints, metadata)


def _risk_parity(returns, constraints, metadata):
    assets = tuple(returns)
    covariance = _covariance(returns)
    weights = {asset: 1.0 / len(assets) for asset in assets}
    for _ in range(300):
        marginal = {
            asset: sum(covariance[asset][other] * weights[other] for other in assets)
            for asset in assets
        }
        contributions = {
            asset: max(weights[asset] * marginal[asset], 1e-12) for asset in assets
        }
        target = mean(contributions.values())
        updated = {
            asset: weights[asset] * sqrt(target / contributions[asset]) for asset in assets
        }
        total = sum(updated.values())
        updated = {asset: value / total for asset, value in updated.items()}
        if max(abs(updated[asset] - weights[asset]) for asset in assets) < 1e-8:
            break
        weights = updated
    return _project(weights, constraints, metadata)


def _hierarchical_risk_parity(returns, constraints, metadata):
    assets = tuple(returns)
    covariance = _covariance(returns)
    correlations = _correlations(returns, covariance)
    order = _correlation_order(assets, correlations)
    weights = {asset: 1.0 for asset in assets}
    clusters = [order]
    while clusters:
        cluster = clusters.pop(0)
        if len(cluster) <= 1:
            continue
        midpoint = len(cluster) // 2
        left, right = cluster[:midpoint], cluster[midpoint:]
        left_variance = _cluster_variance(left, covariance)
        right_variance = _cluster_variance(right, covariance)
        alpha = right_variance / max(left_variance + right_variance, 1e-12)
        for asset in left:
            weights[asset] *= alpha
        for asset in right:
            weights[asset] *= 1.0 - alpha
        clusters.extend((left, right))
    return _project(weights, constraints, metadata)


def _black_litterman_proxy(returns, constraints, metadata):
    """Conservative BL proxy when capitalisation and explicit views are absent.

    The equilibrium prior is equal-risk and the weak view is trailing
    risk-adjusted return. Production use should replace the view with DCF,
    relative-valuation and quality scores.
    """

    stats = _asset_statistics(returns)
    view_values = [values["mean"] / max(values["volatility"], 1e-12) for values in stats.values()]
    center = mean(view_values)
    scale = max(stdev(view_values) if len(view_values) > 1 else 1.0, 1e-12)
    scores = {
        asset: 0.75 + 0.25 * tanh((values["mean"] / max(values["volatility"], 1e-12) - center) / scale)
        for asset, values in stats.items()
    }
    return _project(scores, constraints, metadata)


def _project(scores, constraints, metadata):
    return dict(project_weights(scores, constraints, metadata))


def _asset_statistics(returns):
    result = {}
    for asset, values in returns.items():
        values = tuple(float(value) for value in values)
        losses = sorted(value for value in values if value < 0)
        tail_count = max(1, ceil(0.05 * len(values)))
        tail = sorted(values)[:tail_count]
        result[asset] = {
            "mean": mean(values),
            "volatility": max(_stdev(values), 1e-12),
            "expected_shortfall": max(-mean(tail), 1e-4),
            "downside": max(-mean(losses), 1e-4) if losses else 1e-4,
        }
    return result


def _covariance(returns):
    assets = tuple(returns)
    means = {asset: mean(float(value) for value in returns[asset]) for asset in assets}
    return {
        left: {
            right: sum(
                (float(a) - means[left]) * (float(b) - means[right])
                for a, b in zip(returns[left], returns[right])
            )
            / max(len(returns[left]) - 1, 1)
            for right in assets
        }
        for left in assets
    }


def _correlations(returns, covariance):
    assets = tuple(returns)
    vols = {asset: sqrt(max(covariance[asset][asset], 1e-12)) for asset in assets}
    return {
        left: {
            right: covariance[left][right] / max(vols[left] * vols[right], 1e-12)
            for right in assets
        }
        for left in assets
    }


def _correlation_order(assets, correlations):
    remaining = set(assets)
    first = min(remaining, key=lambda asset: mean(correlations[asset].values()))
    order = [first]
    remaining.remove(first)
    while remaining:
        next_asset = min(
            remaining,
            key=lambda asset: min(1.0 - correlations[asset][selected] for selected in order),
        )
        order.append(next_asset)
        remaining.remove(next_asset)
    return order


def _cluster_variance(cluster, covariance):
    inverse = {asset: 1.0 / max(covariance[asset][asset], 1e-12) for asset in cluster}
    total = sum(inverse.values())
    weights = {asset: value / total for asset, value in inverse.items()}
    return max(
        sum(
            weights[left] * weights[right] * covariance[left][right]
            for left in cluster
            for right in cluster
        ),
        1e-12,
    )


def _turnover(weights, previous):
    if not previous:
        return 0.0
    assets = set(weights) | set(previous)
    cash = 1.0 - sum(weights.values())
    previous_cash = 1.0 - sum(previous.values())
    return 0.5 * (
        sum(abs(weights.get(asset, 0.0) - previous.get(asset, 0.0)) for asset in assets)
        + abs(cash - previous_cash)
    )


def _effective_assets(weights):
    invested = sum(weights.values())
    if invested <= 0:
        return 0.0
    return 1.0 / sum((weight / invested) ** 2 for weight in weights.values())


def _expected_shortfall(values):
    tail = sorted(values)[: max(1, ceil(0.05 * len(values)))]
    return max(0.0, -mean(tail))


def _max_drawdown(wealth):
    peak = wealth[0]
    maximum = 0.0
    for value in wealth:
        peak = max(peak, value)
        maximum = min(maximum, value / peak - 1.0)
    return maximum


def _stdev(values):
    return stdev(values) if len(values) > 1 else 0.0


def _validate_returns(returns):
    if len(returns) < 2:
        raise ValueError("at least two assets are required")
    lengths = {len(values) for values in returns.values()}
    if len(lengths) != 1 or next(iter(lengths)) < 30:
        raise ValueError("returns need equal lengths and at least 30 observations")
    if any(
        not isfinite(float(value)) or float(value) <= -1
        for values in returns.values()
        for value in values
    ):
        raise ValueError("returns must be finite and greater than -1")


def _validate_windows(estimation, validation, live):
    _validate_returns(estimation)
    _validate_returns(validation)
    _validate_returns(live)
    assets = set(estimation)
    if assets != set(validation) or assets != set(live):
        raise ValueError("all windows must contain the same assets")
