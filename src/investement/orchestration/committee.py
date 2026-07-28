from collections.abc import Sequence
from math import sqrt
from statistics import mean

from investement.domain import SignalAction
from investement.orchestration.models import AgentFinding, CommitteeDecision


class InvestmentCommittee:
    def decide(self, findings: Sequence[AgentFinding]) -> CommitteeDecision:
        if len(findings) < 2:
            raise ValueError("the committee requires at least two findings")
        subjects = {finding.subject for finding in findings}
        if len(subjects) != 1:
            raise ValueError("all findings must address the same subject")
        total_confidence = sum(finding.confidence for finding in findings)
        score = (
            sum(finding.score * finding.confidence for finding in findings) / total_confidence
            if total_confidence > 0
            else 0.0
        )
        vetoes = tuple(finding.agent for finding in findings if finding.risk_veto)
        action = SignalAction.HOLD if vetoes else _action_for_score(score)
        dispersion = sqrt(mean((finding.score - score) ** 2 for finding in findings))
        base_confidence = mean(finding.confidence for finding in findings)
        confidence = max(0.0, min(1.0, base_confidence * (1 - min(dispersion, 1.0))))
        dissent = tuple(
            finding.agent
            for finding in findings
            if abs(finding.score - score) >= 0.50
            or (score > 0 and finding.score < 0)
            or (score < 0 and finding.score > 0)
        )
        rationale = _rationale(score, action, vetoes, dissent)
        return CommitteeDecision(
            subject=findings[0].subject,
            action=action,
            score=score,
            confidence=confidence,
            rationale=rationale,
            dissenting_agents=dissent,
            risk_vetoed_by=vetoes,
            findings=tuple(findings),
        )


def _action_for_score(score: float) -> SignalAction:
    if score >= 0.35:
        return SignalAction.BUY
    if score >= -0.10:
        return SignalAction.HOLD
    if score >= -0.35:
        return SignalAction.REDUCE
    return SignalAction.SELL


def _rationale(
    score: float,
    action: SignalAction,
    vetoes: Sequence[str],
    dissent: Sequence[str],
) -> str:
    parts = [f"Weighted committee score {score:.3f} supports {action.value}."]
    if vetoes:
        parts.append(f"Risk veto from {', '.join(vetoes)} blocks an actionable recommendation.")
    if dissent:
        parts.append(f"Material dissent recorded from {', '.join(dissent)}.")
    return " ".join(parts)
