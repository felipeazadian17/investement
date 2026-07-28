from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from investement.agents.auditor import AuditorAgent
from investement.agents.data import DataAgent
from investement.agents.fundamental import FundamentalAgent
from investement.agents.models import (
    AssetAnalysisReport,
    AssetAnalysisRequest,
    BrokerAccountSnapshot,
    InvestorProfile,
    InvestorProfileRequest,
    PortfolioConstructionInputs,
    PortfolioRecommendation,
)
from investement.agents.portfolio import PortfolioConstructionAgent
from investement.agents.profile import InvestorProfileAgent
from investement.agents.relative_valuation import RelativeValuationAgent
from investement.agents.risk import RiskAgent
from investement.agents.schwab import SchwabExecutorAgent
from investement.agents.technical import TechnicalAgent
from investement.orchestration import InvestmentCommittee


class InvestmentAgentPipeline:
    def __init__(
        self,
        data_agent: DataAgent,
        auditor: AuditorAgent | None = None,
        schwab_agent: SchwabExecutorAgent | None = None,
        profile_agent: InvestorProfileAgent | None = None,
        fundamental_agent: FundamentalAgent | None = None,
        technical_agent: TechnicalAgent | None = None,
        relative_valuation_agent: RelativeValuationAgent | None = None,
        portfolio_agent: PortfolioConstructionAgent | None = None,
        risk_agent: RiskAgent | None = None,
        committee: InvestmentCommittee | None = None,
    ) -> None:
        self._data = data_agent
        self._auditor = auditor
        self._schwab = schwab_agent
        self._profile = profile_agent or InvestorProfileAgent()
        self._fundamental = fundamental_agent or FundamentalAgent()
        self._technical = technical_agent or TechnicalAgent()
        self._relative = relative_valuation_agent or RelativeValuationAgent()
        self._portfolio = portfolio_agent or PortfolioConstructionAgent()
        self._risk = risk_agent or RiskAgent()
        self._committee = committee or InvestmentCommittee()

    def create_profile(self, request: InvestorProfileRequest) -> InvestorProfile:
        return self._profile.create(request)

    def analyze_asset(
        self,
        request: AssetAnalysisRequest,
        run_id: str | None = None,
    ) -> AssetAnalysisReport:
        active_run_id = run_id or str(uuid4())
        try:
            snapshot = self._data.collect(request.data)
            fundamental = self._fundamental.analyze(snapshot, request.fundamentals)
            technical = self._technical.analyze(snapshot)
            relative = self._relative.analyze(
                snapshot,
                fundamental,
                request.relative_valuation,
            )
            risk = self._risk.assess_asset(
                request.profile,
                snapshot,
                technical,
                proposed_weight=request.proposed_weight,
            )
            decision = self._committee.decide(
                (
                    fundamental.finding,
                    technical.finding,
                    relative.finding,
                    risk.finding,
                )
            )
            report = AssetAnalysisReport(
                run_id=active_run_id,
                symbol=snapshot.symbol,
                snapshot=snapshot,
                fundamental=fundamental,
                technical=technical,
                relative_valuation=relative,
                risk=risk,
                decision=decision,
            )
            receipt = self._record_asset_report(report)
            return replace(report, audit_receipt=receipt)
        except Exception as exc:
            if self._auditor is not None:
                self._auditor.record(
                    active_run_id,
                    "asset-analysis.failed",
                    {
                        "symbol": request.data.symbol,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            raise

    def construct_portfolio(
        self,
        inputs: PortfolioConstructionInputs,
        as_of: datetime,
        run_id: str | None = None,
    ) -> PortfolioRecommendation:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        active_run_id = run_id or str(uuid4())
        plan = self._portfolio.construct(inputs)
        risk = self._risk.assess_portfolio(inputs.profile, plan, as_of)
        recommendation = PortfolioRecommendation(
            plan=plan,
            risk=risk,
            approved=risk.approved,
        )
        if self._auditor is not None:
            self._auditor.record(
                active_run_id,
                "portfolio.recommended",
                {
                    "as_of": as_of,
                    "backend": plan.allocation.backend,
                    "weights": plan.allocation.weights,
                    "cash_weight": plan.allocation.cash_weight,
                    "risk_approved": risk.approved,
                    "risk_breaches": risk.breaches,
                },
                memory_key=f"portfolio.{as_of.date().isoformat()}",
            )
        return recommendation

    def read_broker_portfolio(
        self,
        include_positions: bool = True,
        run_id: str | None = None,
    ) -> BrokerAccountSnapshot:
        if self._schwab is None:
            raise RuntimeError("Schwab read-only agent is not configured")
        active_run_id = run_id or str(uuid4())
        snapshot = self._schwab.read_portfolio(include_positions=include_positions)
        if self._auditor is not None:
            self._auditor.record(
                active_run_id,
                "schwab.portfolio-read",
                {
                    "retrieved_at": snapshot.retrieved_at,
                    "account_count": len(snapshot.accounts),
                    "account_number_count": len(snapshot.account_numbers),
                    "include_positions": include_positions,
                },
            )
        return snapshot

    def _record_asset_report(self, report: AssetAnalysisReport):
        if self._auditor is None:
            return None
        return self._auditor.record(
            report.run_id,
            "asset-analysis.completed",
            {
                "symbol": report.symbol,
                "as_of": report.snapshot.as_of,
                "current_price": report.snapshot.latest_price,
                "dcf_value": report.fundamental.dcf.value_per_share,
                "blended_fair_value": report.relative_valuation.blended_fair_value,
                "decision": report.decision.action.value,
                "committee_score": report.decision.score,
                "committee_confidence": report.decision.confidence,
                "risk_approved": report.risk.approved,
                "risk_breaches": report.risk.breaches,
                "findings": [_finding_summary(item) for item in report.decision.findings],
            },
            memory_key=f"analysis.{report.symbol}",
        )


def _finding_summary(finding) -> dict[str, Any]:
    return {
        "agent": finding.agent,
        "score": finding.score,
        "confidence": finding.confidence,
        "thesis": finding.thesis,
        "risks": tuple(finding.risks),
        "risk_veto": finding.risk_veto,
        "evidence": [
            {
                "source": item.source,
                "reference": item.reference,
                "observed_at": item.observed_at,
            }
            for item in finding.evidence
        ],
    }
