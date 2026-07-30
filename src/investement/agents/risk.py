from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from statistics import mean

from investement.agents.models import (
    AssetDataSnapshot,
    BrokerPortfolioState,
    InvestorProfile,
    PortfolioPlan,
    RiskAssessment,
    TechnicalAnalysis,
    TechnicalTimingAction,
)
from investement.data import normalize_symbol
from investement.orchestration import AgentFinding, EvidenceReference
from investement.portfolio import AssetMetadata


class RiskAgent:
    name = "risk"

    def assess_asset(
        self,
        profile: InvestorProfile,
        snapshot: AssetDataSnapshot,
        technical: TechnicalAnalysis,
        proposed_weight: float = 0.0,
    ) -> RiskAssessment:
        if not isfinite(proposed_weight) or not 0 <= proposed_weight <= 1:
            raise ValueError("proposed_weight must be between zero and one")
        average_daily_dollar_volume = mean(
            bar.adjusted_close * bar.volume for bar in snapshot.bars[-20:]
        )
        breaches = []
        warnings = list(technical.finding.risks)
        if snapshot.symbol in profile.prohibited_symbols:
            breaches.append("symbol is prohibited by the investor profile")
        if proposed_weight > profile.max_position_weight + 1e-10:
            breaches.append("proposed position exceeds the maximum position weight")
        if technical.annual_volatility > profile.max_annual_volatility:
            breaches.append("asset volatility exceeds the investor profile limit")
        if technical.max_drawdown > profile.max_asset_drawdown:
            breaches.append("observed drawdown exceeds the investor profile limit")
        if average_daily_dollar_volume < profile.minimum_daily_dollar_volume:
            breaches.append("average daily dollar volume is below the liquidity floor")
        if technical.timing.action is TechnicalTimingAction.FAVOR_EXIT:
            warnings.append("technical timing currently favors reducing or exiting the position")
        elif technical.timing.action is TechnicalTimingAction.TIGHTEN_RISK:
            warnings.append("technical timing indicates partial deterioration")
        metrics = {
            "proposed_weight": proposed_weight,
            "annual_volatility": technical.annual_volatility,
            "max_drawdown": technical.max_drawdown,
            "current_drawdown": technical.current_drawdown,
            "normalized_atr": technical.normalized_atr,
            "average_daily_dollar_volume": average_daily_dollar_volume,
        }
        return _assessment(
            subject=snapshot.symbol,
            breaches=breaches,
            metrics=metrics,
            evidence=tuple(snapshot.evidence),
            observed_at=snapshot.as_of,
            warnings=warnings,
        )

    def assess_portfolio(
        self,
        profile: InvestorProfile,
        plan: PortfolioPlan,
        as_of: datetime,
    ) -> RiskAssessment:
        breaches = []
        maximum_weight = max(plan.allocation.weights.values(), default=0.0)
        if maximum_weight > profile.max_position_weight + 1e-10:
            breaches.append("portfolio contains a position above the profile maximum")
        if plan.allocation.annual_volatility > profile.max_portfolio_annual_volatility:
            breaches.append("portfolio volatility exceeds the investor profile limit")
        if plan.allocation.historical_max_drawdown > profile.max_drawdown:
            breaches.append("historical portfolio drawdown exceeds the investor profile limit")
        if abs(sum(plan.allocation.weights.values()) + plan.allocation.cash_weight - 1) > 1e-7:
            breaches.append("portfolio weights and cash do not sum to one")
        breaches.extend(_group_limit_breaches(profile, plan.allocation.group_exposures))
        warnings = list(plan.allocation.warnings)
        if len(plan.allocation.weights) >= 3 and plan.allocation.effective_number_of_assets < 3:
            warnings.append("effective number of invested assets is below three")
        metrics = {
            "annual_volatility": plan.allocation.annual_volatility,
            "expected_annual_return": plan.allocation.expected_annual_return,
            "maximum_position_weight": maximum_weight,
            "cash_weight": plan.allocation.cash_weight,
            "historical_var_95": plan.allocation.historical_var_95,
            "historical_expected_shortfall_95": (
                plan.allocation.historical_expected_shortfall_95
            ),
            "historical_max_drawdown": plan.allocation.historical_max_drawdown,
            "effective_number_of_assets": plan.allocation.effective_number_of_assets,
            "turnover": plan.allocation.turnover or 0.0,
            "observations": float(plan.allocation.observations),
        }
        evidence = (
            EvidenceReference(
                source="deterministic-portfolio-risk",
                reference=f"model://portfolio-risk/{as_of.isoformat()}",
                observed_at=as_of,
            ),
        )
        return _assessment(
            subject="portfolio",
            breaches=breaches,
            metrics=metrics,
            evidence=evidence,
            observed_at=as_of,
            warnings=warnings,
        )

    def assess_current_portfolio(
        self,
        profile: InvestorProfile,
        state: BrokerPortfolioState,
        metadata: Mapping[str, AssetMetadata] | None = None,
    ) -> RiskAssessment:
        breaches = []
        maximum_weight = max(state.current_weights.values(), default=0.0)
        concentrated = sorted(
            symbol
            for symbol, weight in state.current_weights.items()
            if weight > profile.max_position_weight + 1e-10
        )
        if concentrated:
            breaches.append(
                "current positions exceed the profile maximum: " + ", ".join(concentrated)
            )
        prohibited = sorted(set(state.current_weights) & profile.prohibited_symbols)
        if prohibited:
            breaches.append("current portfolio contains prohibited symbols: " + ", ".join(prohibited))
        if state.cash_weight + 1e-10 < profile.min_cash_weight:
            breaches.append("current cash is below the investor profile minimum")
        if sum(state.current_weights.values()) + state.cash_weight > 1 + 1e-7:
            breaches.append("current positions and cash exceed total portfolio value")
        exposures = _current_group_exposures(state.current_weights, metadata or {})
        breaches.extend(_group_limit_breaches(profile, exposures))
        residual_weight = max(
            0.0,
            1.0 - state.cash_weight - sum(state.current_weights.values()),
        )
        warnings = []
        if residual_weight > 1e-6:
            warnings.append("broker total contains value not classified as cash or supported positions")
        metrics = {
            "total_value": state.total_value,
            "invested_weight": sum(state.current_weights.values()),
            "maximum_position_weight": maximum_weight,
            "cash_weight": state.cash_weight,
            "unclassified_weight": residual_weight,
        }
        evidence = (
            EvidenceReference(
                source="broker-portfolio",
                reference=(
                    f"broker://{state.provider}/snapshot/{state.retrieved_at.isoformat()}"
                ),
                observed_at=state.retrieved_at,
            ),
        )
        return _assessment(
            subject="current-portfolio",
            breaches=breaches,
            metrics=metrics,
            evidence=evidence,
            observed_at=state.retrieved_at,
            warnings=warnings,
        )


def _assessment(
    subject: str,
    breaches: list[str],
    metrics: dict[str, float],
    evidence: tuple[EvidenceReference, ...],
    observed_at: datetime,
    warnings: list[str] | tuple[str, ...] = (),
) -> RiskAssessment:
    approved = not breaches
    score = 0.0 if approved else max(-1.0, -0.45 - 0.15 * len(breaches))
    thesis = (
        "No hard risk limit was breached."
        if approved
        else f"Hard risk limits breached: {'; '.join(breaches)}."
    )
    finding = AgentFinding(
        agent="risk",
        subject=subject,
        score=score,
        confidence=0.95,
        thesis=thesis,
        evidence=evidence
        or (
            EvidenceReference(
                source="deterministic-risk",
                reference=f"model://risk/{subject}",
                observed_at=observed_at,
            ),
        ),
        risks=tuple(breaches) + tuple(dict.fromkeys(warnings)),
        invalidation_conditions=("Any hard risk metric crosses its configured limit",),
        risk_veto=not approved,
    )
    return RiskAssessment(
        subject=subject,
        approved=approved,
        breaches=tuple(breaches),
        metrics=metrics,
        finding=finding,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _group_limit_breaches(
    profile: InvestorProfile,
    exposures: Mapping[str, Mapping[str, float]],
) -> list[str]:
    breaches = []
    policies = (
        ("sector", profile.sector_max_weights),
        ("country", profile.country_max_weights),
        ("asset_class", profile.asset_class_max_weights),
        ("currency", profile.currency_max_weights),
    )
    for family, limits in policies:
        observed = exposures.get(family, {})
        for group, limit in limits.items():
            if observed.get(group, 0.0) > limit + 1e-8:
                breaches.append(f"{family} {group} exceeds the profile limit")
    return breaches


def _current_group_exposures(
    weights: Mapping[str, float],
    metadata: Mapping[str, AssetMetadata],
) -> Mapping[str, Mapping[str, float]]:
    normalized_metadata = {
        normalize_symbol(symbol): value for symbol, value in metadata.items()
    }
    result: dict[str, dict[str, float]] = {}
    for family in ("sector", "country", "asset_class", "currency"):
        groups: dict[str, float] = {}
        for symbol, weight in weights.items():
            value = getattr(normalized_metadata.get(normalize_symbol(symbol)), family, None)
            if value:
                key = str(value).strip().casefold()
                groups[key] = groups.get(key, 0.0) + weight
        result[family] = groups
    return result
