from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from investement.agents.auditor import AuditorAgent
from investement.agents.broker import BrokerPortfolioReader, BrokerPortfolioStateReader
from investement.agents.data import DataAgent
from investement.agents.fundamental import FundamentalAgent
from investement.agents.models import (
    AssetAnalysisReport,
    AssetAnalysisRequest,
    BrokerAccountSnapshot,
    BrokerAwarePortfolioRecommendation,
    InvestorProfile,
    InvestorProfileRequest,
    PortfolioConstructionInputs,
    PortfolioRecommendation,
)
from investement.agents.portfolio import PortfolioConstructionAgent
from investement.agents.profile import InvestorProfileAgent
from investement.agents.relative_valuation import RelativeValuationAgent
from investement.agents.risk import RiskAgent
from investement.agents.technical import TechnicalAgent
from investement.orchestration import InvestmentCommittee
from investement.valuation import InsufficientComparablePeers, MarketWACCBuilder


class InvestmentAgentPipeline:
    def __init__(
        self,
        data_agent: DataAgent,
        auditor: AuditorAgent | None = None,
        broker_agent: BrokerPortfolioReader | None = None,
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
        self._broker = broker_agent
        self._profile = profile_agent or InvestorProfileAgent()
        self._fundamental = fundamental_agent or FundamentalAgent(
            MarketWACCBuilder(data_agent.market_data_provider)
        )
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
            fundamental = self._fundamental.analyze(snapshot)
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
                failure = {
                    "symbol": request.data.symbol,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                if isinstance(exc, InsufficientComparablePeers):
                    failure["peer_selection"] = _peer_selection_summary(exc.result)
                self._auditor.record(
                    active_run_id,
                    "asset-analysis.failed",
                    failure,
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
                    "risk_warnings": risk.warnings,
                    "historical_var_95": plan.allocation.historical_var_95,
                    "historical_expected_shortfall_95": (
                        plan.allocation.historical_expected_shortfall_95
                    ),
                    "historical_max_drawdown": plan.allocation.historical_max_drawdown,
                    "effective_number_of_assets": plan.allocation.effective_number_of_assets,
                    "turnover": plan.allocation.turnover,
                    "group_exposures": plan.allocation.group_exposures,
                    "return_date_start": (
                        inputs.return_dates[0] if inputs.return_dates else None
                    ),
                    "return_date_end": (
                        inputs.return_dates[-1] if inputs.return_dates else None
                    ),
                },
                memory_key=f"portfolio.{as_of.date().isoformat()}",
            )
        return recommendation

    def read_broker_portfolio(
        self,
        include_positions: bool = True,
        run_id: str | None = None,
    ) -> BrokerAccountSnapshot:
        if self._broker is None:
            raise RuntimeError("read-only broker agent is not configured")
        active_run_id = run_id or str(uuid4())
        snapshot = self._broker.read_portfolio(include_positions=include_positions)
        if self._auditor is not None:
            self._auditor.record(
                active_run_id,
                "broker.portfolio-read",
                {
                    "provider": self._broker.name,
                    "retrieved_at": snapshot.retrieved_at,
                    "account_count": len(snapshot.accounts),
                    "account_number_count": len(snapshot.account_numbers),
                    "include_positions": include_positions,
                },
            )
        return snapshot

    def construct_portfolio_from_broker(
        self,
        inputs: PortfolioConstructionInputs,
        as_of: datetime,
        run_id: str | None = None,
    ) -> BrokerAwarePortfolioRecommendation:
        if not isinstance(self._broker, BrokerPortfolioStateReader):
            raise TypeError("configured broker does not provide normalized portfolio state")
        active_run_id = run_id or str(uuid4())
        current = self._broker.current_portfolio(inputs.profile.base_currency)
        current_risk = self._risk.assess_current_portfolio(
            inputs.profile,
            current,
            inputs.metadata,
        )
        target = self.construct_portfolio(
            replace(inputs, current_weights={}),
            as_of,
            run_id=active_run_id,
        )
        if self._auditor is not None:
            self._auditor.record(
                active_run_id,
                "broker.portfolio-reconciled",
                {
                    "provider": current.provider,
                    "allocation_mode": "initial-independent",
                    "retrieved_at": current.retrieved_at,
                    "base_currency": current.base_currency,
                    "total_value": current.total_value,
                    "cash_weight": current.cash_weight,
                    "current_weights": current.current_weights,
                    "current_risk_approved": current_risk.approved,
                    "current_risk_breaches": current_risk.breaches,
                },
            )
        return BrokerAwarePortfolioRecommendation(
            current=current,
            current_risk=current_risk,
            target=target,
        )

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
                "technical": {
                    "score": report.technical.finding.score,
                    "confidence": report.technical.finding.confidence,
                    "regime": report.technical.trend_regime.value,
                    "timing_action": report.technical.timing.action.value,
                    "timing_strength": report.technical.timing.strength,
                    "timing_confidence": report.technical.timing.confidence,
                    "timing_observed_at": report.technical.timing.observed_at,
                    "timing_valid_for_bars": report.technical.timing.valid_for_bars,
                    "execute_on_next_bar": report.technical.timing.execute_on_next_bar,
                    "timing_reasons": tuple(report.technical.timing.reasons),
                    "parameters": dict(report.technical.parameters),
                },
                "peer_selection": _peer_selection_summary(
                    report.relative_valuation.peer_selection
                ),
                "decision": report.decision.action.value,
                "committee_score": report.decision.score,
                "committee_confidence": report.decision.confidence,
                "committee_effective_weights": report.decision.effective_weights,
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


def _peer_selection_summary(selection) -> dict[str, Any] | None:
    if selection is None:
        return None
    return {
        "target_symbol": selection.target_symbol,
        "metric": selection.metric,
        "selected": [
            {
                "symbol": item.symbol,
                "similarity_score": item.similarity_score,
                "feature_coverage": item.feature_coverage,
                "family_scores": dict(item.family_scores),
                "reasons": tuple(item.reasons),
            }
            for item in selection.selected
        ],
        "eligible_not_selected": tuple(
            item.symbol for item in selection.eligible_not_selected
        ),
        "rejected": [
            {"symbol": item.symbol, "reason": item.reason} for item in selection.rejected
        ],
    }
