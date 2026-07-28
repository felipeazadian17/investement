from investement.agents.models import (
    AssetDataSnapshot,
    FundamentalAnalysis,
    RelativeValuationAnalysis,
    RelativeValuationInputs,
)
from investement.orchestration import AgentFinding, EvidenceReference
from investement.valuation import valuation_signal, value_from_comparables


class RelativeValuationAgent:
    name = "relative-valuation"

    def analyze(
        self,
        snapshot: AssetDataSnapshot,
        fundamental: FundamentalAnalysis,
        inputs: RelativeValuationInputs,
    ) -> RelativeValuationAnalysis:
        comparable_result = value_from_comparables(
            target_metric_value=inputs.target_metric_value,
            observations=inputs.comparables,
            metric=inputs.metric,
        )
        blended_value = (
            fundamental.dcf.value_per_share * inputs.dcf_weight
            + comparable_result.value_per_share * (1 - inputs.dcf_weight)
        )
        confidence = min(
            0.95,
            fundamental.finding.confidence * 0.70 + min(comparable_result.peer_count / 10, 0.30),
        )
        risks = list(fundamental.finding.risks)
        if comparable_result.excluded_outliers:
            risks.append(
                "Comparable outliers excluded: " + ", ".join(comparable_result.excluded_outliers)
            )
        signal = valuation_signal(
            current_price=snapshot.latest_price,
            fair_value=blended_value,
            confidence=confidence,
            required_margin=inputs.required_margin,
            sell_premium=inputs.sell_premium,
            risks=tuple(risks),
            invalidation_conditions=(
                "Peer group is no longer economically comparable",
                "DCF or target operating metric changes materially",
            ),
        )
        denominator = (
            inputs.required_margin if signal.margin_of_safety >= 0 else inputs.sell_premium
        )
        score = _clamp(signal.margin_of_safety / max(denominator, 1e-12))
        evidence = tuple(snapshot.evidence) + (
            EvidenceReference(
                source="deterministic-comparables",
                reference=(
                    f"model://comparables/{snapshot.symbol}/"
                    f"{inputs.metric.lower().replace(' ', '-')}"
                ),
                observed_at=snapshot.as_of,
            ),
        )
        finding = AgentFinding(
            agent=self.name,
            subject=snapshot.symbol,
            score=score,
            confidence=confidence,
            thesis=(
                f"Blended fair value is {blended_value:.2f} versus "
                f"{snapshot.latest_price:.2f}, a margin of safety of "
                f"{signal.margin_of_safety:.1%}."
            ),
            evidence=evidence,
            risks=signal.risks,
            invalidation_conditions=signal.invalidation_conditions,
        )
        return RelativeValuationAnalysis(
            comparables=comparable_result,
            blended_fair_value=blended_value,
            signal=signal,
            finding=finding,
        )


def _clamp(value: float) -> float:
    return max(-1.0, min(float(value), 1.0))
