from collections.abc import Mapping, Sequence
from math import isfinite

from investement.agents.models import (
    InvestorProfile,
    PortfolioConstructionInputs,
    PortfolioPlan,
    RebalanceInstruction,
)
from investement.data import normalize_symbol
from investement.domain import SignalAction
from investement.portfolio import AssetMetadata, PortfolioConstraints, PortfolioRequest
from investement.portfolio.optimizers import RobustPortfolioOptimizer


class PortfolioConstructionAgent:
    name = "portfolio-construction"

    def __init__(self, optimizer: RobustPortfolioOptimizer | None = None) -> None:
        self._optimizer = optimizer or RobustPortfolioOptimizer()

    def construct(self, inputs: PortfolioConstructionInputs) -> PortfolioPlan:
        returns = _normalized_mapping(inputs.returns)
        metadata = {
            normalize_symbol(symbol): _normalized_metadata(value)
            for symbol, value in inputs.metadata.items()
        }
        current_weights = {
            normalize_symbol(symbol): float(value)
            for symbol, value in inputs.current_weights.items()
        }
        if any(not isfinite(value) or not 0 <= value <= 1 for value in current_weights.values()):
            raise ValueError("current weights must be finite and between zero and one")
        if sum(current_weights.values()) > 1 + 1e-8:
            raise ValueError("current weights cannot exceed total portfolio capital")
        decisions = {
            normalize_symbol(symbol): decision for symbol, decision in inputs.decisions.items()
        }
        eligible = {}
        excluded = {}
        asset_limits = {}
        for symbol, series in returns.items():
            reason = _exclusion_reason(symbol, metadata.get(symbol), inputs.profile, decisions)
            if reason is not None:
                excluded[symbol] = reason
                continue
            decision = decisions.get(symbol)
            if decision is not None and decision.action == SignalAction.REDUCE:
                current = current_weights.get(symbol, 0.0)
                if current <= 0:
                    excluded[symbol] = "reduce decision with no current position"
                    continue
                asset_limits[symbol] = min(inputs.profile.max_position_weight, current)
            eligible[symbol] = series
        if len(eligible) < 2:
            raise ValueError("portfolio construction requires at least two eligible assets")

        constraints = _constraints(inputs.profile, asset_limits)
        allocation = self._optimizer.optimize(
            PortfolioRequest(
                returns=eligible,
                constraints=constraints,
                metadata={symbol: metadata[symbol] for symbol in eligible if symbol in metadata},
                current_weights={symbol: current_weights.get(symbol, 0.0) for symbol in eligible},
                return_dates=inputs.return_dates,
            ),
            backend=inputs.backend,
        )
        mandatory_exits = set(excluded) & set(current_weights)
        rebalances = _rebalance_instructions(
            allocation.weights,
            current_weights,
            inputs.absolute_rebalance_band,
            inputs.relative_rebalance_band,
            mandatory_exits,
        )
        return PortfolioPlan(
            allocation=allocation,
            rebalances=rebalances,
            eligible_assets=tuple(sorted(eligible)),
            excluded_assets=dict(sorted(excluded.items())),
            implementation_turnover=_implementation_turnover(rebalances),
        )


def _normalized_mapping(values: Mapping[str, Sequence[float]]) -> dict[str, Sequence[float]]:
    normalized = {}
    for symbol, series in values.items():
        key = normalize_symbol(symbol)
        if key in normalized:
            raise ValueError(f"duplicate symbol after normalization: {key}")
        normalized[key] = series
    return normalized


def _exclusion_reason(
    symbol: str,
    metadata: AssetMetadata | None,
    profile: InvestorProfile,
    decisions: Mapping,
) -> str | None:
    if symbol in profile.prohibited_symbols:
        return "symbol prohibited by investor profile"
    if metadata is not None:
        if metadata.sector and metadata.sector.casefold() in profile.prohibited_sectors:
            return "sector prohibited by investor profile"
        if metadata.country and metadata.country.casefold() in profile.prohibited_countries:
            return "country prohibited by investor profile"
    decision = decisions.get(symbol)
    if decision is not None and decision.action == SignalAction.SELL:
        return "committee sell decision"
    if decision is not None and decision.risk_vetoed_by:
        return "committee recommendation blocked by risk veto"
    return None


def _constraints(
    profile: InvestorProfile,
    asset_limits: Mapping[str, float],
) -> PortfolioConstraints:
    return PortfolioConstraints(
        max_weight=profile.max_position_weight,
        min_cash=profile.min_cash_weight,
        asset_max_weights=dict(asset_limits),
        sector_max_weights=dict(profile.sector_max_weights),
        country_max_weights=dict(profile.country_max_weights),
        asset_class_max_weights=dict(profile.asset_class_max_weights),
        currency_max_weights=dict(profile.currency_max_weights),
        max_annual_volatility=profile.max_portfolio_annual_volatility,
    )


def _normalized_metadata(value: AssetMetadata) -> AssetMetadata:
    return AssetMetadata(
        sector=value.sector.strip().casefold() if value.sector else None,
        country=value.country.strip().casefold() if value.country else None,
        asset_class=value.asset_class.strip().casefold() if value.asset_class else None,
        currency=value.currency.strip().casefold() if value.currency else None,
    )


def _rebalance_instructions(
    target_weights: Mapping[str, float],
    current_weights: Mapping[str, float],
    absolute_band: float,
    relative_band: float,
    mandatory_exits: set[str],
) -> tuple[RebalanceInstruction, ...]:
    instructions = []
    for symbol in sorted(set(target_weights) | set(current_weights)):
        current = current_weights.get(symbol, 0.0)
        target = target_weights.get(symbol, 0.0)
        change = target - current
        threshold = max(absolute_band, relative_band * max(target, current))
        if current_weights and symbol not in mandatory_exits and abs(change) <= threshold:
            target = current
            change = 0.0
        if change > 1e-8:
            action = SignalAction.BUY
        elif change < -1e-8:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD
        instructions.append(
            RebalanceInstruction(
                symbol=symbol,
                current_weight=current,
                target_weight=target,
                change=change,
                action=action,
            )
        )
    return tuple(instructions)


def _implementation_turnover(instructions: Sequence[RebalanceInstruction]) -> float:
    if not instructions:
        return 0.0
    current_cash = max(0.0, 1.0 - sum(item.current_weight for item in instructions))
    target_cash = max(0.0, 1.0 - sum(item.target_weight for item in instructions))
    return 0.5 * (
        sum(abs(item.change) for item in instructions) + abs(target_cash - current_cash)
    )
