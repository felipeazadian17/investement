import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from investement.agents import (
    AssetAnalysisRequest,
    AssetDataRequest,
    AuditorAgent,
    BrokerAccountSnapshot,
    BrokerPortfolioState,
    DataAgent,
    FundamentalAgent,
    InvestmentAgentPipeline,
    InvestmentExperience,
    InvestorProfileAgent,
    InvestorProfileRequest,
    LeveragePolicy,
    PortfolioConstructionAgent,
    PortfolioConstructionInputs,
    RelativeValuationAgent,
    RelativeValuationInputs,
    RiskAgent,
    RiskTolerance,
    TaxPolicy,
    TechnicalAgent,
)
from investement.agents.portfolio import _rebalance_instructions
from investement.domain import (
    CorporateActionKind,
    DataProvenance,
    FundamentalSnapshot,
    PriceBar,
    SignalAction,
)
from investement.orchestration import (
    AgentFinding,
    CommitteeDecision,
    EvidenceReference,
    JsonlAuditLog,
    JsonMemoryStore,
)
from investement.portfolio import AssetMetadata
from investement.valuation import (
    ComparableObservation,
    CreditSpreadObservation,
    FixedCreditSpreadProvider,
    FixedMarketRateProvider,
    MarketRateObservation,
    MarketWACCBuilder,
    PeerProfile,
)


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
        self.calls = []

    def latest_filings(
        self,
        symbol,
        forms,
        limit=10,
        filed_after=None,
        available_before=None,
    ):
        self.calls.append((symbol, forms, limit, filed_after, available_before))
        return self.filings[:limit]


class FakeFundamentalProvider:
    name = "fake-fundamentals"

    def __init__(self, fundamentals):
        self.fundamentals = fundamentals

    def latest_fundamentals(self, symbol, forms, limit=8, **kwargs):
        return self.fundamentals[:limit]


class FakePortfolioStateBroker:
    name = "fake-read-only-broker"

    def read_portfolio(self, include_positions=True):
        return BrokerAccountSnapshot(
            retrieved_at=datetime(2024, 4, 1, tzinfo=UTC),
            account_numbers=(),
            accounts=({"include_positions": include_positions},),
        )

    def current_portfolio(self, base_currency="USD"):
        return BrokerPortfolioState(
            retrieved_at=datetime(2024, 4, 1, tzinfo=UTC),
            provider=self.name,
            base_currency=base_currency,
            total_value=100_000,
            cash_value=10_000,
            cash_weight=0.10,
            position_values={"A": 70_000, "B": 20_000},
            current_weights={"A": 0.70, "B": 0.20},
        )


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

    def test_profile_agent_derives_personal_risk_and_reserve_constraints(self):
        profile = _profile_agent().create_from_mapping(
            {
                "objectives": ["Long-term capital growth with continuous reinvestment"],
                "horizon_years": 20,
                "base_currency": "USD",
                "min_cash_weight": 0.05,
                "max_position_weight": 0.10,
                "max_drawdown": 0.20,
                "max_annual_volatility": 0.55,
                "max_portfolio_annual_volatility": 0.18,
                "max_asset_drawdown": 0.50,
                "age": 29,
                "residence_country": "UY",
                "tax_residency": "UY",
                "monthly_net_income": 4_000,
                "monthly_expenses": 1_500,
                "liquid_net_worth": 80_000,
                "portfolio_funding": 80_000,
                "external_emergency_reserve": 0,
                "emergency_fund_months_target": 6,
                "dependents": 0,
                "income_stability": "stable",
                "investment_experience": "expert",
                "short_selling_allowed": False,
                "leverage_policy": "exceptional",
                "preferred_styles": ["value", "quality", "dividend-growth"],
                "prefers_dividends": True,
                "requires_fixed_income": False,
                "profile_as_of": "2026-07-28",
                "tax_policy": {
                    "jurisdiction": "UY",
                    "rules_as_of": "2026-07-24",
                    "foreign_investment_income_taxable": True,
                    "foreign_capital_gains_taxable": True,
                    "foreign_tax_credit_available": True,
                    "tax_lot_method": "weighted-average",
                    "us_situs_estate_tax_threshold": 60_000,
                    "prefer_non_us_domiciled_funds": True,
                },
            }
        )
        self.assertEqual(profile.risk_assessment.capacity, RiskTolerance.AGGRESSIVE)
        self.assertEqual(profile.risk_assessment.willingness, RiskTolerance.MODERATE)
        self.assertEqual(profile.risk_tolerance, RiskTolerance.MODERATE)
        self.assertEqual(profile.risk_assessment.capacity_score, 10)
        self.assertEqual(profile.monthly_surplus, 2_500)
        self.assertEqual(profile.emergency_reserve_target, 9_000)
        self.assertEqual(profile.investable_assets_after_reserve, 71_000)
        self.assertAlmostEqual(profile.min_cash_weight, 0.1125)
        self.assertEqual(profile.max_position_weight, 0.06)
        self.assertEqual(profile.max_portfolio_annual_volatility, 0.18)
        self.assertEqual(profile.max_asset_drawdown, 0.50)
        self.assertEqual(profile.investment_experience, InvestmentExperience.EXPERT)
        self.assertEqual(profile.leverage_policy, LeveragePolicy.EXCEPTIONAL)
        self.assertFalse(profile.short_selling_allowed)
        self.assertTrue(profile.tax_policy.foreign_capital_gains_taxable)
        self.assertEqual(profile.tax_policy.rules_as_of, date(2026, 7, 24))

    def test_profile_agent_rejects_tax_policy_for_another_residency(self):
        with self.assertRaisesRegex(ValueError, "tax policy jurisdiction"):
            _profile_agent().create(
                InvestorProfileRequest(
                    objectives=("Long-term growth",),
                    horizon_years=20,
                    base_currency="USD",
                    tax_residency="UY",
                    tax_policy=TaxPolicy(
                        jurisdiction="AR",
                        rules_as_of=date(2026, 7, 24),
                    ),
                )
            )

    def test_data_agent_enforces_as_of_for_prices_and_filings(self):
        bars = _bars(61)
        as_of = bars[-2].timestamp
        past_filing = _filing("10-Q", as_of - timedelta(days=5))
        future_filing = _filing("8-K", as_of + timedelta(days=1))
        market = FakeMarketDataProvider(bars)
        filings = FakeFilingProvider((past_filing, future_filing))
        snapshot = DataAgent(
            market,
            filings,
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
        self.assertIsNone(filings.calls[0][3])
        self.assertTrue(all(bar.timestamp <= as_of for bar in snapshot.bars))

    def test_data_agent_exposes_corporate_actions_and_uses_raw_latest_price(self):
        bars = list(_bars(2))
        bars[1] = replace(
            bars[1],
            adjusted_close=bars[1].close + 5.0,
            provenance=replace(
                bars[1].provenance,
                metadata={"dividend": 0.25, "stock_split": 2.0},
            ),
        )
        snapshot = DataAgent(
            FakeMarketDataProvider(tuple(bars)),
            clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
        ).collect(
            AssetDataRequest(
                symbol="AAPL",
                start=bars[0].timestamp.date(),
                end=bars[-1].timestamp.date(),
                as_of=bars[-1].timestamp,
            )
        )
        self.assertEqual(snapshot.latest_price, bars[-1].close)
        self.assertEqual(
            tuple(action.kind for action in snapshot.corporate_actions),
            (CorporateActionKind.DIVIDEND, CorporateActionKind.SPLIT),
        )

    def test_analyst_agents_produce_compatible_structured_findings(self):
        snapshot = _snapshot()
        fundamentals = _fundamental_agent(FakeMarketDataProvider(snapshot.bars)).analyze(snapshot)
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
        self.assertAlmostEqual(
            fundamentals.model_assumptions["initial_revenue_growth"],
            0.10,
        )
        self.assertGreaterEqual(technical.rsi, 0)
        self.assertLessEqual(technical.rsi, 100)
        self.assertEqual(relative.signal.action, SignalAction.BUY)
        self.assertIsNotNone(relative.comparable_signal)
        self.assertIn("Comparable fair value", relative.finding.thesis)

    def test_relative_valuation_agent_selects_peers_from_candidate_universe(self):
        snapshot = _snapshot()
        fundamentals = _fundamental_agent(FakeMarketDataProvider(snapshot.bars)).analyze(snapshot)
        target = _peer_profile("AAPL")
        candidates = tuple(
            ComparableObservation(
                symbol,
                multiple,
                "P/FCF",
                replace(target, symbol=symbol),
            )
            for symbol, multiple in (
                ("B", 12.0),
                ("C", 13.0),
                ("D", 14.0),
                ("E", 15.0),
                ("F", 16.0),
            )
        )
        relative = RelativeValuationAgent().analyze(
            snapshot,
            fundamentals,
            RelativeValuationInputs(
                target_metric_value=2.0,
                metric="P/FCF",
                comparables=candidates,
                target_peer_profile=target,
            ),
        )
        self.assertIsNotNone(relative.peer_selection)
        self.assertEqual(len(relative.peer_selection.selected), 5)
        self.assertFalse(any("supplied manually" in risk for risk in relative.finding.risks))

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

    def test_risk_approval_is_directionally_neutral(self):
        snapshot = _snapshot()
        technical = TechnicalAgent().analyze(snapshot)
        profile = _profile_agent().create(_profile_request())

        assessment = RiskAgent().assess_asset(profile, snapshot, technical, 0.05)

        self.assertTrue(assessment.approved)
        self.assertEqual(assessment.finding.score, 0.0)

    def test_rebalance_band_suppresses_small_trades_but_not_mandatory_exits(self):
        instructions = _rebalance_instructions(
            {"A": 0.31, "B": 0.0},
            {"A": 0.30, "B": 0.02},
            absolute_band=0.02,
            relative_band=0.20,
            mandatory_exits={"B"},
        )
        indexed = {item.symbol: item for item in instructions}

        self.assertEqual(indexed["A"].action, SignalAction.HOLD)
        self.assertEqual(indexed["A"].change, 0.0)
        self.assertEqual(indexed["B"].action, SignalAction.SELL)

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
        bars = _bars(260, daily_step=0.034)
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
                    fundamentals=FakeFundamentalProvider(_fundamental_snapshots()),
                    clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
                ),
                auditor=auditor,
                fundamental_agent=_fundamental_agent(FakeMarketDataProvider(bars)),
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
                broker_agent=FakePortfolioStateBroker(),
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

    def test_pipeline_builds_initial_allocation_independent_of_broker_positions(self):
        pipeline = InvestmentAgentPipeline(
            DataAgent(FakeMarketDataProvider(_bars(90))),
            broker_agent=FakePortfolioStateBroker(),
        )
        profile = pipeline.create_profile(
            _profile_request(max_position_weight=0.60, max_annual_volatility=1.0)
        )
        result = pipeline.construct_portfolio_from_broker(
            PortfolioConstructionInputs(
                profile=profile,
                returns={
                    "A": (0.01, 0.02, -0.01, 0.01),
                    "B": (0.001, 0.002, 0.0015, 0.0025),
                },
            ),
            as_of=datetime(2024, 4, 1, tzinfo=UTC),
        )
        rebalance = {item.symbol: item for item in result.target.plan.rebalances}
        self.assertFalse(result.current_risk.approved)
        self.assertIn("A", result.current_risk.breaches[0])
        self.assertEqual(result.current.current_weights["A"], 0.70)
        self.assertEqual(rebalance["A"].current_weight, 0.0)
        self.assertTrue(result.target.approved)


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


def _bars(count: int, daily_step: float = 0.10) -> tuple[PriceBar, ...]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    retrieved = datetime(2025, 1, 1, tzinfo=UTC)
    bars = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        close = 10.0 + index * daily_step + (0.05 if index % 2 else -0.03)
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
    bars = _bars(260, daily_step=0.034)
    return DataAgent(
        FakeMarketDataProvider(bars),
        fundamentals=FakeFundamentalProvider(_fundamental_snapshots()),
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


def _fundamental_snapshots() -> tuple[FundamentalSnapshot, ...]:
    retrieved_at = datetime(2024, 3, 30, tzinfo=UTC)

    def annual(year, revenue, ebit, available_at):
        return FundamentalSnapshot(
            symbol="AAPL",
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
            period_basis="fiscal-year",
            filing_type="10-K",
            currency="USD",
            revenue=revenue,
            ebit=ebit,
            operating_cash_flow=25.0,
            capital_expenditure=5.0,
            cash_and_equivalents=20.0,
            total_debt=15.0,
            diluted_shares=10.0,
            current_shares_outstanding=9.8,
            net_income=15.0,
            pretax_income=20.0,
            income_tax_expense=4.2,
            interest_expense=1.0,
            short_term_investments=3.0,
            long_term_investments=2.0,
            operating_lease_liabilities=1.0,
            total_equity=80.0,
            total_assets=130.0,
            provenance=DataProvenance(
                source="sec-edgar-xbrl",
                retrieved_at=retrieved_at,
                available_at=available_at,
                raw_reference=f"fixture://10-k/{year}",
                metadata={"accession_number": f"10-k-{year}", "company_sic": "3571"},
            ),
        )

    return (
        annual(2023, 110.0, 24.0, datetime(2024, 2, 1, tzinfo=UTC)),
        annual(2022, 100.0, 20.0, datetime(2023, 2, 1, tzinfo=UTC)),
    )


def _fundamental_agent(market_data) -> FundamentalAgent:
    rates = FixedMarketRateProvider(
        MarketRateObservation(
            observed_at=date(2024, 1, 1),
            risk_free_rate=0.04,
            equity_risk_premium=0.05,
            source_url="fixture://market-rates",
        )
    )
    spreads = FixedCreditSpreadProvider(
        CreditSpreadObservation(
            observed_at=date(2024, 1, 1),
            thresholds=((float("inf"), 0.01),),
            source_url="fixture://credit-spreads",
        )
    )
    return FundamentalAgent(
        MarketWACCBuilder(
            market_data,
            rate_provider=rates,
            minimum_beta_observations=2,
            credit_spread_provider=spreads,
        )
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


def _peer_profile(symbol: str) -> PeerProfile:
    return PeerProfile(
        symbol=symbol,
        company_type="operating-company",
        sector="Information Technology",
        industry="Technology Hardware",
        lifecycle="mature",
        metrics={
            "revenue_growth": 0.08,
            "ebit_margin": 0.28,
            "capex_to_revenue": 0.04,
            "revenue": 100_000.0,
            "beta": 1.0,
        },
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
