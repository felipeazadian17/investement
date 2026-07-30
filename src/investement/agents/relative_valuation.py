from investement.agents.models import (
    AssetDataSnapshot,
    FundamentalAnalysis,
    RelativeValuationAnalysis,
    RelativeValuationInputs,
)
from investement.orchestration import AgentFinding, EvidenceReference
from investement.valuation import (
    select_comparable_peers,
    valuation_signal,
    value_from_comparables,
)


class RelativeValuationAgent:
    name = "relative-valuation"

    def analyze(
        self,
        snapshot: AssetDataSnapshot,
        fundamental: FundamentalAnalysis,
        inputs: RelativeValuationInputs,
    ) -> RelativeValuationAnalysis:
        peer_selection = None
        observations = inputs.comparables
        if inputs.target_peer_profile is not None:
            if inputs.target_peer_profile.symbol.casefold() != snapshot.symbol.casefold():
                raise ValueError("target peer profile must match the analyzed asset")
            peer_selection = select_comparable_peers(
                target=inputs.target_peer_profile,
                observations=inputs.comparables,
                metric=inputs.metric,
                config=inputs.peer_selection_config,
            )
            observations = peer_selection.observations
        comparable_result = value_from_comparables(
            target_metric_value=inputs.target_metric_value,
            observations=observations,
            metric=inputs.metric,
            enterprise_to_equity_adjustment_per_share=(
                inputs.enterprise_to_equity_adjustment_per_share
            ),
        )
        blended_value = (
            fundamental.dcf.value_per_share * inputs.dcf_weight
            + comparable_result.value_per_share * (1 - inputs.dcf_weight)
        )
        if peer_selection is not None:
            average_similarity = sum(
                item.similarity_score for item in peer_selection.selected
            ) / len(peer_selection.selected)
            peer_confidence = min(comparable_result.peer_count / 10, 0.20) + (
                0.10 * average_similarity
            )
        else:
            peer_confidence = min(comparable_result.peer_count / 10, 0.30)
        confidence = min(
            0.95,
            fundamental.finding.confidence * 0.70 + peer_confidence,
        )
        comparable_confidence = min(0.85, 0.40 + peer_confidence)
        comparable_risks = []
        if comparable_result.excluded_outliers:
            comparable_risks.append(
                "Comparable outliers excluded: " + ", ".join(comparable_result.excluded_outliers)
            )
        if peer_selection is None:
            comparable_risks.append(
                "Peer universe was supplied manually; economic similarity was not scored"
            )
        risks = list(fundamental.finding.risks) + comparable_risks
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
        comparable_signal = valuation_signal(
            current_price=snapshot.latest_price,
            fair_value=comparable_result.value_per_share,
            confidence=comparable_confidence,
            required_margin=inputs.required_margin,
            sell_premium=inputs.sell_premium,
            risks=tuple(comparable_risks),
            invalidation_conditions=("Peer group is no longer economically comparable",),
        )
        denominator = (
            inputs.required_margin
            if comparable_signal.margin_of_safety >= 0
            else inputs.sell_premium
        )
        score = _clamp(comparable_signal.margin_of_safety / max(denominator, 1e-12))
        evidence_source = (
            "deterministic-peer-selection"
            if peer_selection is not None
            else "deterministic-comparables"
        )
        evidence = tuple(snapshot.evidence) + (
            EvidenceReference(
                source=evidence_source,
                reference=(
                    f"model://comparables/{snapshot.symbol}/"
                    f"{inputs.metric.lower().replace(' ', '-')}"
                ),
                observed_at=snapshot.as_of,
            ),
        )
        peer_description = (
            f" using {comparable_result.peer_count} automatically selected peers"
            if peer_selection is not None
            else f" using {comparable_result.peer_count} manually supplied peers"
        )
        finding = AgentFinding(
            agent=self.name,
            subject=snapshot.symbol,
            score=score,
            confidence=comparable_confidence,
            thesis=(
                f"Comparable fair value is {comparable_result.value_per_share:.2f} versus "
                f"{snapshot.latest_price:.2f}{peer_description}, a margin of safety of "
                f"{comparable_signal.margin_of_safety:.1%}; blended DCF/comparable value "
                f"is {blended_value:.2f}."
            ),
            evidence=evidence,
            risks=comparable_signal.risks,
            invalidation_conditions=comparable_signal.invalidation_conditions,
        )
        return RelativeValuationAnalysis(
            comparables=comparable_result,
            blended_fair_value=blended_value,
            signal=signal,
            finding=finding,
            peer_selection=peer_selection,
            comparable_signal=comparable_signal,
        )


def _clamp(value: float) -> float:
    return max(-1.0, min(float(value), 1.0))
