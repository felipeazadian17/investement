from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite

from investement.domain import SignalAction, require_aware


@dataclass(frozen=True)
class EvidenceReference:
    source: str
    reference: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.reference.strip():
            raise ValueError("evidence source and reference are required")
        require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True)
class AgentFinding:
    agent: str
    subject: str
    score: float
    confidence: float
    thesis: str
    evidence: Sequence[EvidenceReference]
    risks: Sequence[str] = ()
    invalidation_conditions: Sequence[str] = ()
    risk_veto: bool = False

    def __post_init__(self) -> None:
        if not self.agent.strip() or not self.subject.strip() or not self.thesis.strip():
            raise ValueError("agent, subject and thesis are required")
        if not isfinite(self.score) or not -1 <= self.score <= 1:
            raise ValueError("score must be between -1 and 1")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence:
            raise ValueError("at least one evidence reference is required")


@dataclass(frozen=True)
class CommitteeDecision:
    subject: str
    action: SignalAction
    score: float
    confidence: float
    rationale: str
    dissenting_agents: Sequence[str]
    risk_vetoed_by: Sequence[str]
    findings: Sequence[AgentFinding]
    effective_weights: Mapping[str, float] = field(default_factory=dict)
