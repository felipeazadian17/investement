from datetime import datetime
from statistics import mean

from investement.agents.models import (
    AssetDataSnapshot,
    BrokerPortfolioState,
    InvestorProfile,
    PortfolioPlan,
    RiskAssessment,
    TechnicalAnalysis,
)
from investement.orchestration import AgentFinding, EvidenceReference


class RiskAgent:
    name = "risk"

    def assess_asset(
        self,
        profile: InvestorProfile,
        snapshot: AssetDataSnapshot,
        technical: TechnicalAnalysis,
        proposed_weight: float = 0.0,
    ) -> RiskAssessment:
        average_daily_dollar_volume = mean(
            bar.adjusted_close * bar.volume for bar in snapshot.bars[-20:]
        )
        breaches = []
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
        metrics = {
            "proposed_weight": proposed_weight,
            "annual_volatility": technical.annual_volatility,
            "max_drawdown": technical.max_drawdown,
            "average_daily_dollar_volume": average_daily_dollar_volume,
        }
        return _assessment(
            subject=snapshot.symbol,
            breaches=breaches,
            metrics=metrics,
            evidence=tuple(snapshot.evidence),
            observed_at=snapshot.as_of,
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
        if abs(sum(plan.allocation.weights.values()) + plan.allocation.cash_weight - 1) > 1e-7:
            breaches.append("portfolio weights and cash do not sum to one")
        metrics = {
            "annual_volatility": plan.allocation.annual_volatility,
            "expected_annual_return": plan.allocation.expected_annual_return,
            "maximum_position_weight": maximum_weight,
            "cash_weight": plan.allocation.cash_weight,
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
        )

    def assess_current_portfolio(
        self,
        profile: InvestorProfile,
        state: BrokerPortfolioState,
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
        metrics = {
            "total_value": state.total_value,
            "invested_weight": sum(state.current_weights.values()),
            "maximum_position_weight": maximum_weight,
            "cash_weight": state.cash_weight,
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
        )


def _assessment(
    subject: str,
    breaches: list[str],
    metrics: dict[str, float],
    evidence: tuple[EvidenceReference, ...],
    observed_at: datetime,
) -> RiskAssessment:
    approved = not breaches
    score = 0.20 if approved else max(-1.0, -0.45 - 0.15 * len(breaches))
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
        risks=tuple(breaches),
        invalidation_conditions=("Any hard risk metric crosses its configured limit",),
        risk_veto=not approved,
    )
    return RiskAssessment(
        subject=subject,
        approved=approved,
        breaches=tuple(breaches),
        metrics=metrics,
        finding=finding,
    )
