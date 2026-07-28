from math import tanh
from statistics import mean

from investement.agents.models import (
    AssetDataSnapshot,
    FundamentalAnalysis,
    FundamentalModelInputs,
)
from investement.orchestration import AgentFinding, EvidenceReference
from investement.valuation import DCFInputs, discounted_cash_flow, project_cash_flows


class FundamentalAgent:
    name = "fundamental"

    def analyze(
        self,
        snapshot: AssetDataSnapshot,
        inputs: FundamentalModelInputs,
    ) -> FundamentalAnalysis:
        projected = project_cash_flows(inputs.base_free_cash_flow, inputs.growth_rates)
        dcf = discounted_cash_flow(
            DCFInputs(
                projected_free_cash_flows=projected,
                discount_rate=inputs.discount_rate,
                terminal_growth_rate=inputs.terminal_growth_rate,
                net_debt=inputs.net_debt,
                diluted_shares=inputs.diluted_shares,
            )
        )
        quality_score = _quality_score(inputs)
        valuation_gap = (dcf.value_per_share - snapshot.latest_price) / max(
            abs(dcf.value_per_share), 1e-12
        )
        score = _clamp(0.70 * tanh(valuation_gap / 0.30) + 0.30 * quality_score)
        risks = []
        if dcf.terminal_value_share > 0.75:
            risks.append("More than 75% of enterprise value comes from terminal value")
        if inputs.base_free_cash_flow <= 0:
            risks.append("Base free cash flow is not positive")
        if inputs.debt_to_free_cash_flow is not None and inputs.debt_to_free_cash_flow > 4:
            risks.append("Debt exceeds four times free cash flow")
        confidence = _confidence(inputs, dcf.terminal_value_share)
        evidence = tuple(snapshot.evidence) + (
            EvidenceReference(
                source="deterministic-dcf",
                reference=f"model://dcf/{snapshot.symbol}/{snapshot.as_of.date().isoformat()}",
                observed_at=snapshot.as_of,
            ),
        )
        finding = AgentFinding(
            agent=self.name,
            subject=snapshot.symbol,
            score=score,
            confidence=confidence,
            thesis=(
                f"DCF estimates {dcf.value_per_share:.2f} per share versus "
                f"{snapshot.latest_price:.2f}; quality score is {quality_score:.2f}."
            ),
            evidence=evidence,
            risks=tuple(risks),
            invalidation_conditions=(
                "Free cash flow falls materially below the modeled path",
                "Discount rate no longer reflects the company's risk",
            ),
        )
        return FundamentalAnalysis(
            dcf=dcf,
            projected_free_cash_flows=projected,
            quality_score=quality_score,
            finding=finding,
        )


def _quality_score(inputs: FundamentalModelInputs) -> float:
    components = []
    if inputs.roic is not None:
        components.append(_clamp((inputs.roic - inputs.discount_rate) / 0.10))
    if inputs.revenue_growth is not None:
        components.append(_clamp(inputs.revenue_growth / 0.15))
    if inputs.operating_margin is not None:
        components.append(_clamp((inputs.operating_margin - 0.10) / 0.20))
    if inputs.debt_to_free_cash_flow is not None:
        components.append(_clamp((3.0 - inputs.debt_to_free_cash_flow) / 3.0))
    return mean(components) if components else 0.0


def _confidence(inputs: FundamentalModelInputs, terminal_share: float) -> float:
    supplied_metrics = sum(
        value is not None
        for value in (
            inputs.roic,
            inputs.revenue_growth,
            inputs.operating_margin,
            inputs.debt_to_free_cash_flow,
        )
    )
    confidence = 0.55 + supplied_metrics * 0.075
    if terminal_share > 0.75:
        confidence -= min((terminal_share - 0.75) * 0.60, 0.20)
    return max(0.20, min(confidence, 0.90))


def _clamp(value: float) -> float:
    return max(-1.0, min(float(value), 1.0))
