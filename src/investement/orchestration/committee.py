from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite, sqrt

from investement.domain import SignalAction
from investement.orchestration.models import AgentFinding, CommitteeDecision


@dataclass(frozen=True)
class CommitteePolicy:
    agent_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "fundamental": 0.70,
            "relative-valuation": 0.30,
            "technical": 0.0,
            "risk": 0.0,
        }
    )
    minimum_actionable_confidence: float = 0.35
    buy_threshold: float = 0.35
    reduce_threshold: float = -0.10
    sell_threshold: float = -0.35

    def __post_init__(self) -> None:
        if any(not isfinite(value) or value < 0 for value in self.agent_weights.values()):
            raise ValueError("committee agent weights must be finite and non-negative")
        if not 0 <= self.minimum_actionable_confidence <= 1:
            raise ValueError("minimum_actionable_confidence must be between zero and one")
        if not -1 <= self.sell_threshold < self.reduce_threshold < self.buy_threshold <= 1:
            raise ValueError(
                "committee thresholds must satisfy sell < reduce < buy within [-1, 1]"
            )


class InvestmentCommittee:
    def __init__(self, policy: CommitteePolicy | None = None) -> None:
        self._policy = policy or CommitteePolicy()

    def decide(self, findings: Sequence[AgentFinding]) -> CommitteeDecision:
        if len(findings) < 2:
            raise ValueError("the committee requires at least two findings")
        subjects = {finding.subject for finding in findings}
        if len(subjects) != 1:
            raise ValueError("all findings must address the same subject")
        agents = [finding.agent for finding in findings]
        if len(agents) != len(set(agents)):
            raise ValueError("committee findings must contain unique agents")
        raw_weights = {
            finding.agent: self._policy.agent_weights.get(finding.agent, 1.0)
            for finding in findings
        }
        total_policy_weight = sum(raw_weights.values())
        if total_policy_weight <= 0:
            raise ValueError("committee findings have no positive policy weight")
        effective_weights = {
            agent: weight / total_policy_weight for agent, weight in raw_weights.items()
        }
        total_confidence = sum(
            finding.confidence * effective_weights[finding.agent] for finding in findings
        )
        score = (
            sum(
                finding.score * finding.confidence * effective_weights[finding.agent]
                for finding in findings
            )
            / total_confidence
            if total_confidence > 0
            else 0.0
        )
        vetoes = tuple(finding.agent for finding in findings if finding.risk_veto)
        suggested_action = _action_for_score(score, self._policy)
        action = SignalAction.HOLD if vetoes else suggested_action
        dispersion = sqrt(
            sum(
                effective_weights[finding.agent] * (finding.score - score) ** 2
                for finding in findings
            )
        )
        base_confidence = total_confidence
        confidence = max(0.0, min(1.0, base_confidence * (1 - min(dispersion, 1.0))))
        confidence_blocked = (
            not vetoes
            and action is not SignalAction.HOLD
            and confidence < self._policy.minimum_actionable_confidence
        )
        if confidence_blocked:
            action = SignalAction.HOLD
        dissent = tuple(
            finding.agent
            for finding in findings
            if abs(finding.score - score) >= 0.50
            or (score > 0 and finding.score < 0)
            or (score < 0 and finding.score > 0)
        )
        rationale = _rationale(
            score,
            suggested_action,
            action,
            vetoes,
            dissent,
            confidence_blocked,
        )
        return CommitteeDecision(
            subject=findings[0].subject,
            action=action,
            score=score,
            confidence=confidence,
            rationale=rationale,
            dissenting_agents=dissent,
            risk_vetoed_by=vetoes,
            findings=tuple(findings),
            effective_weights=effective_weights,
        )


def _action_for_score(score: float, policy: CommitteePolicy) -> SignalAction:
    if score >= policy.buy_threshold:
        return SignalAction.BUY
    if score >= policy.reduce_threshold:
        return SignalAction.HOLD
    if score >= policy.sell_threshold:
        return SignalAction.REDUCE
    return SignalAction.SELL


def _rationale(
    score: float,
    suggested_action: SignalAction,
    action: SignalAction,
    vetoes: Sequence[str],
    dissent: Sequence[str],
    confidence_blocked: bool,
) -> str:
    parts = [f"Weighted committee score {score:.3f} supports {suggested_action.value}."]
    if vetoes:
        parts.append(f"Risk veto from {', '.join(vetoes)} blocks an actionable recommendation.")
    if confidence_blocked:
        parts.append("Recommendation was downgraded to hold because confidence is below policy.")
    if dissent:
        parts.append(f"Material dissent recorded from {', '.join(dissent)}.")
    if action is not suggested_action and not vetoes and not confidence_blocked:
        parts.append(f"Governance policy changed the final action to {action.value}.")
    return " ".join(parts)
