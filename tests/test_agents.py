import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from investement.agents import (
    AssetAnalysisRequest,
    AssetDataRequest,
    AuditorAgent,
    DataAgent,
    FundamentalAgent,
    FundamentalModelInputs,
    InvestmentAgentPipeline,
    InvestorProfileAgent,
    InvestorProfileRequest,
    PortfolioConstructionAgent,
    PortfolioConstructionInputs,
    RelativeValuationAgent,
    RelativeValuationInputs,
    RiskAgent,
    RiskTolerance,
    SchwabExecutorAgent,
    TechnicalAgent,
)
from investement.domain import DataProvenance, PriceBar, SignalAction
from investement.orchestration import (
    AgentFinding,
    CommitteeDecision,
    EvidenceReference,
    JsonlAuditLog,
    JsonMemoryStore,
)
from investement.portfolio import AssetMetadata
from investement.valuation import ComparableObservation


class FakeMarketDataProvider:
    name = "fake-market"

    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def history(self, symbol, start, end, interval="1d"):
        self.calls.append((symbol, start, end, interval))
        return self.bars


class FakeFilingProvider:
    name = "fake-filings"

    def __init__(self, filings):
        self.filings = filings

    def latest_filings(self, symbol, forms, limit=10, filed_after=None):
        return self.filings[:limit]


class FakeSchwabFacade:
    def account_numbers(self):
        return ({"accountNumber": "1234", "hashValue": "hash"},)

    def accounts(self, include_positions=True):
        return ({"securitiesAccount": {"positions": [] if include_positions else None}},)

    def account(self, account_hash, include_positions=True):
        return {"hash": account_hash, "include_positions": include_positions}

    def transactions(self, *args, **kwargs):
        return ({"type": "DIVIDEND"},)

    def quotes(self, symbols):
        return {symbol: {"lastPrice": 100.0} for symbol in symbols}


class AgentTests(unittest.TestCase):
    def test_profile_agent_normalizes_constraints_and_sets_risk_default(self):
        profile = _profile_agent().create(
            InvestorProfileRequest(
                objectives=("Retirement",),
                horizon_years=15,
                base_currency="usd",
                risk_tolerance=RiskTolerance.CONSERVATIVE,
                prohibited_symbols=(" tsla ",),
                prohibited_sectors=("Tobacco",),
            )
        )
        self.assertEqual(profile.base_currency, "USD")
        self.assertEqual(profile.max_annual_volatility, 0.20)
        self.assertIn("TSLA", profile.prohibited_symbols)
        self.assertIn("tobacco", profile.prohibited_sectors)

    def test_data_agent_enforces_as_of_for_prices_and_filings(self):
        bars = _bars(61)
        as_of = bars[-2].timestamp
        past_filing = _filing("10-Q", as_of - timedelta(days=5))
        future_filing = _filing("8-K", as_of + timedelta(days=1))
        market = FakeMarketDataProvider(bars)
        snapshot = DataAgent(
            market,
            FakeFilingProvider((past_filing, future_filing)),
            clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
        ).collect(
            AssetDataRequest(
                symbol="aapl.us",
                start=bars[0].timestamp.date(),
                end=(as_of + timedelta(days=10)).date(),
                as_of=as_of,
            )
        )
        self.assertEqual(snapshot.symbol, "AAPL")
        self.assertEqual(len(snapshot.bars), 60)
        self.assertEqual(snapshot.filings, (past_filing,))
        self.assertEqual(market.calls[0][2], as_of.date())
        self.assertTrue(all(bar.timestamp <= as_of for bar in snapshot.bars))

    def test_analyst_agents_produce_compatible_structured_findings(self):
        snapshot = _snapshot()
        fundamentals = FundamentalAgent().analyze(snapshot, _fundamental_inputs())
        technical = TechnicalAgent().analyze(snapshot)
        relative = RelativeValuationAgent().analyze(
            snapshot,
            fundamentals,
            _relative_inputs(),
        )
        self.assertEqual(fundamentals.finding.subject, "AAPL")
        self.assertEqual(technical.finding.subject, "AAPL")
        self.assertEqual(relative.finding.subject, "AAPL")
        self.assertGreater(fundamentals.dcf.value_per_share, 0)
        self.assertGreaterEqual(technical.rsi, 0)
        self.assertLessEqual(technical.rsi, 100)
        self.assertEqual(relative.signal.action, SignalAction.BUY)

    def test_risk_agent_vetoes_an_asset_that_breaches_profile(self):
        snapshot = _snapshot()
        technical = TechnicalAgent().analyze(snapshot)
        profile = _profile_agent().create(
            _profile_request(max_annual_volatility=0.0001, max_position_weight=0.10)
        )
        assessment = RiskAgent().assess_asset(
            profile,
            snapshot,
            technical,
            proposed_weight=0.25,
        )
        self.assertFalse(assessment.approved)
        self.assertTrue(assessment.finding.risk_veto)
        self.assertGreaterEqual(len(assessment.breaches), 2)

    def test_portfolio_agent_applies_profile_and_committee_exclusions(self):
        profile = _profile_agent().create(
            _profile_request(
                max_position_weight=0.60,
                prohibited_symbols=("D",),
            )
        )
        plan = PortfolioConstructionAgent().construct(
            PortfolioConstructionInputs(
                profile=profile,
                returns={
                    "A": (0.01, 0.02, -0.01, 0.01),
                    "B": (0.001, 0.002, 0.0015, 0.0025),
                    "C": (-0.01, -0.02, 0.01, -0.01),
                    "D": (0.02, 0.01, 0.03, 0.01),
                },
                metadata={
                    "A": AssetMetadata("Technology", "US"),
                    "B": AssetMetadata("Healthcare", "US"),
                    "C": AssetMetadata("Industrials", "US"),
                    "D": AssetMetadata("Energy", "US"),
                },
                decisions={
                    "A": _decision("A", SignalAction.BUY),
                    "B": _decision("B", SignalAction.HOLD),
                    "C": _decision("C", SignalAction.SELL),
                },
                current_weights={"A": 0.20, "B": 0.30, "C": 0.20, "D": 0.10},
            )
        )
        self.assertEqual(set(plan.eligible_assets), {"A", "B"})
        self.assertIn("C", plan.excluded_assets)
        self.assertIn("D", plan.excluded_assets)
        self.assertAlmostEqual(sum(plan.allocation.weights.values()), 0.95)

    def test_schwab_executor_agent_has_read_capabilities_only(self):
        agent = SchwabExecutorAgent(
            FakeSchwabFacade(),
            clock=lambda: datetime(2024, 1, 1, tzinfo=UTC),
        )
        snapshot = agent.read_portfolio()
        self.assertEqual(len(snapshot.accounts), 1)
        self.assertEqual(agent.read_account("hash")["hash"], "hash")
        self.assertFalse(hasattr(agent, "place_order"))
        self.assertFalse(hasattr(agent, "execute"))
        self.assertFalse(hasattr(agent, "cancel_order"))

    def test_auditor_redacts_secrets_and_keeps_a_valid_hash_chain(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory = JsonMemoryStore(root / "memory")
            auditor = AuditorAgent(JsonlAuditLog(root / "audit.jsonl"), memory)
            receipt = auditor.record(
                "run-1",
                "test",
                {
                    "as_of": datetime(2024, 1, 1, tzinfo=UTC),
                    "client_secret": "do-not-store",
                    "nested": {"accessToken": "also-secret", "value": 42},
                },
                memory_key="test.record",
            )
            stored = memory.load("test.record")
        self.assertTrue(receipt.chain_valid)
        self.assertEqual(stored.value["client_secret"], "[REDACTED]")
        self.assertEqual(stored.value["nested"]["accessToken"], "[REDACTED]")
        self.assertEqual(stored.value["as_of"], "2024-01-01T00:00:00+00:00")

    def test_pipeline_runs_profile_through_committee_and_audit(self):
        bars = _bars(90)
        as_of = bars[-1].timestamp
        with TemporaryDirectory() as directory:
            root = Path(directory)
            auditor = AuditorAgent(
                JsonlAuditLog(root / "audit.jsonl"),
                JsonMemoryStore(root / "memory"),
            )
            pipeline = InvestmentAgentPipeline(
                DataAgent(
                    FakeMarketDataProvider(bars),
                    clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
                ),
                auditor=auditor,
            )
            profile = pipeline.create_profile(
                _profile_request(max_position_weight=0.60, max_annual_volatility=1.0)
            )
            report = pipeline.analyze_asset(
                AssetAnalysisRequest(
                    profile=profile,
                    data=AssetDataRequest(
                        symbol="AAPL",
                        start=bars[0].timestamp.date(),
                        end=as_of.date(),
                        as_of=as_of,
                    ),
                    fundamentals=_fundamental_inputs(),
                    relative_valuation=_relative_inputs(),
                    proposed_weight=0.20,
                ),
                run_id="pipeline-run",
            )
            remembered = JsonMemoryStore(root / "memory").load("analysis.AAPL")
        self.assertEqual(report.run_id, "pipeline-run")
        self.assertEqual(len(report.decision.findings), 4)
        self.assertFalse(report.decision.risk_vetoed_by)
        self.assertTrue(report.audit_receipt.chain_valid)
        self.assertEqual(remembered.value["symbol"], "AAPL")

    def test_pipeline_exposes_portfolio_and_read_only_broker_workflows(self):
        bars = _bars(90)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pipeline = InvestmentAgentPipeline(
                DataAgent(FakeMarketDataProvider(bars)),
                auditor=AuditorAgent(
                    JsonlAuditLog(root / "audit.jsonl"),
                    JsonMemoryStore(root / "memory"),
                ),
                schwab_agent=SchwabExecutorAgent(
                    FakeSchwabFacade(),
                    clock=lambda: datetime(2024, 4, 1, tzinfo=UTC),
                ),
            )
            profile = pipeline.create_profile(
                _profile_request(max_position_weight=0.60, max_annual_volatility=1.0)
            )
            recommendation = pipeline.construct_portfolio(
                PortfolioConstructionInputs(
                    profile=profile,
                    returns={
                        "A": (0.01, 0.02, -0.01, 0.01),
                        "B": (0.001, 0.002, 0.0015, 0.0025),
                    },
                ),
                as_of=datetime(2024, 4, 1, tzinfo=UTC),
                run_id="portfolio-run",
            )
            broker = pipeline.read_broker_portfolio(run_id="broker-run")
        self.assertTrue(recommendation.approved)
        self.assertAlmostEqual(
            sum(recommendation.plan.allocation.weights.values())
            + recommendation.plan.allocation.cash_weight,
            1.0,
        )
        self.assertEqual(len(broker.accounts), 1)


def _profile_agent() -> InvestorProfileAgent:
    return InvestorProfileAgent()


def _profile_request(**overrides) -> InvestorProfileRequest:
    values = {
        "objectives": ("Long-term capital growth",),
        "horizon_years": 10,
        "base_currency": "USD",
        "risk_tolerance": RiskTolerance.MODERATE,
        "min_cash_weight": 0.05,
        "max_position_weight": 0.60,
        "max_drawdown": 0.50,
        "max_annual_volatility": 1.0,
    }
    values.update(overrides)
    return InvestorProfileRequest(**values)


def _bars(count: int) -> tuple[PriceBar, ...]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    retrieved = datetime(2025, 1, 1, tzinfo=UTC)
    bars = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        close = 10.0 + index * 0.10 + (0.05 if index % 2 else -0.03)
        bars.append(
            PriceBar(
                symbol="AAPL",
                timestamp=timestamp,
                open=close - 0.05,
                high=close + 0.15,
                low=close - 0.15,
                close=close,
                adjusted_close=close,
                volume=1_000_000,
                currency="USD",
                provenance=DataProvenance(
                    source="fixture",
                    retrieved_at=retrieved,
                    available_at=timestamp,
                    raw_reference=f"fixture://AAPL/{timestamp.date().isoformat()}",
                ),
            )
        )
    return tuple(bars)


def _snapshot():
    bars = _bars(90)
    return DataAgent(
        FakeMarketDataProvider(bars),
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
    ).collect(
        AssetDataRequest(
            symbol="AAPL",
            start=bars[0].timestamp.date(),
            end=bars[-1].timestamp.date(),
            as_of=bars[-1].timestamp,
        )
    )


def _filing(form: str, available_at: datetime):
    return SimpleNamespace(
        form=form,
        filing_date=available_at.date(),
        accession_number=f"{form}-{available_at.date().isoformat()}",
        provenance=DataProvenance(
            source="sec-fixture",
            retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
            available_at=available_at,
            raw_reference=f"fixture://filing/{form}/{available_at.date().isoformat()}",
        ),
    )


def _fundamental_inputs() -> FundamentalModelInputs:
    return FundamentalModelInputs(
        base_free_cash_flow=20.0,
        growth_rates=(0.08, 0.07, 0.06, 0.05, 0.04),
        discount_rate=0.10,
        terminal_growth_rate=0.025,
        net_debt=5.0,
        diluted_shares=10.0,
        roic=0.18,
        revenue_growth=0.09,
        operating_margin=0.22,
        debt_to_free_cash_flow=1.5,
    )


def _relative_inputs() -> RelativeValuationInputs:
    return RelativeValuationInputs(
        target_metric_value=2.0,
        metric="P/FCF",
        comparables=(
            ComparableObservation("B", 12.0, "P/FCF"),
            ComparableObservation("C", 14.0, "P/FCF"),
            ComparableObservation("D", 15.0, "P/FCF"),
            ComparableObservation("OUTLIER", 100.0, "P/FCF"),
        ),
        required_margin=0.15,
    )


def _decision(symbol: str, action: SignalAction) -> CommitteeDecision:
    evidence = EvidenceReference(
        source="test",
        reference=f"fixture://decision/{symbol}",
        observed_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    finding = AgentFinding(
        agent="committee-fixture",
        subject=symbol,
        score=0.5 if action == SignalAction.BUY else 0.0,
        confidence=0.8,
        thesis="Fixture committee decision",
        evidence=(evidence,),
    )
    return CommitteeDecision(
        subject=symbol,
        action=action,
        score=finding.score,
        confidence=finding.confidence,
        rationale="Fixture",
        dissenting_agents=(),
        risk_vetoed_by=(),
        findings=(finding,),
    )


if __name__ == "__main__":
    unittest.main()
