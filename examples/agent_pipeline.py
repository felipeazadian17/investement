from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from investement.agents import (
    AssetAnalysisRequest,
    AssetDataRequest,
    AuditorAgent,
    DataAgent,
    FundamentalAgent,
    InvestmentAgentPipeline,
    InvestorProfileRequest,
    PortfolioConstructionInputs,
    RelativeValuationInputs,
    RiskTolerance,
)
from investement.domain import DataProvenance, FundamentalSnapshot, PriceBar
from investement.orchestration import JsonlAuditLog, JsonMemoryStore
from investement.portfolio import AssetMetadata
from investement.valuation import (
    ComparableObservation,
    CreditSpreadObservation,
    FixedCreditSpreadProvider,
    FixedMarketRateProvider,
    MarketRateObservation,
    MarketWACCBuilder,
)


class SyntheticMarketData:
    name = "synthetic-example"

    def __init__(self, bars):
        self._bars = bars

    def history(self, symbol, start, end, interval="1d"):
        return self._bars


class SyntheticFundamentals:
    name = "synthetic-fundamentals"

    def __init__(self, snapshots):
        self._snapshots = snapshots

    def latest_fundamentals(self, symbol, forms, limit=8, **kwargs):
        return self._snapshots[:limit]


def make_bars(count=260):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    retrieved_at = datetime(2025, 1, 1, tzinfo=UTC)
    bars = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        close = 20 + index * 0.08 + (0.04 if index % 2 else -0.03)
        bars.append(
            PriceBar(
                symbol="ACME",
                timestamp=timestamp,
                open=close - 0.05,
                high=close + 0.15,
                low=close - 0.15,
                close=close,
                adjusted_close=close,
                volume=2_000_000,
                currency="USD",
                provenance=DataProvenance(
                    source="synthetic-example",
                    retrieved_at=retrieved_at,
                    available_at=timestamp,
                    raw_reference=f"example://ACME/{timestamp.date().isoformat()}",
                ),
            )
        )
    return tuple(bars)


def main():
    bars = make_bars()
    as_of = bars[-1].timestamp
    market = SyntheticMarketData(bars)
    fundamentals = make_fundamentals()
    rates = FixedMarketRateProvider(
        MarketRateObservation(date(2024, 1, 1), 0.04, 0.05, "fixture://market-rates")
    )
    spreads = FixedCreditSpreadProvider(
        CreditSpreadObservation(
            date(2024, 1, 1),
            ((float("inf"), 0.01),),
            "fixture://credit-spreads",
        )
    )
    with TemporaryDirectory() as directory:
        artifacts = Path(directory)
        pipeline = InvestmentAgentPipeline(
            DataAgent(
                market,
                fundamentals=SyntheticFundamentals(fundamentals),
                clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
            ),
            auditor=AuditorAgent(
                JsonlAuditLog(artifacts / "audit.jsonl"),
                JsonMemoryStore(artifacts / "memory"),
            ),
            fundamental_agent=FundamentalAgent(
                MarketWACCBuilder(
                    market,
                    rates,
                    minimum_beta_observations=2,
                    credit_spread_provider=spreads,
                )
            ),
        )
        profile = pipeline.create_profile(
            InvestorProfileRequest(
                objectives=("Long-term capital growth",),
                horizon_years=12,
                base_currency="USD",
                risk_tolerance=RiskTolerance.MODERATE,
                max_position_weight=0.50,
                max_annual_volatility=0.60,
            )
        )
        report = pipeline.analyze_asset(
            AssetAnalysisRequest(
                profile=profile,
                data=AssetDataRequest(
                    symbol="ACME",
                    start=bars[0].timestamp.date(),
                    end=as_of.date(),
                    as_of=as_of,
                ),
                relative_valuation=RelativeValuationInputs(
                    target_metric_value=2.5,
                    metric="P/FCF",
                    comparables=(
                        ComparableObservation("PEER1", 12, "P/FCF"),
                        ComparableObservation("PEER2", 14, "P/FCF"),
                        ComparableObservation("PEER3", 15, "P/FCF"),
                    ),
                ),
                proposed_weight=0.25,
            )
        )
        portfolio = pipeline.construct_portfolio(
            PortfolioConstructionInputs(
                profile=profile,
                returns={
                    "ACME": (0.01, 0.015, -0.008, 0.012, 0.006),
                    "BND": (0.002, 0.001, 0.0015, 0.002, 0.001),
                    "VEA": (0.006, -0.002, 0.004, 0.003, 0.005),
                },
                metadata={
                    "ACME": AssetMetadata("Technology", "US"),
                    "BND": AssetMetadata("Fixed Income", "US"),
                    "VEA": AssetMetadata("Diversified", "International"),
                },
                decisions={"ACME": report.decision},
            ),
            as_of=as_of,
        )
        print(
            {
                "asset": report.symbol,
                "decision": report.decision.action.value,
                "committee_score": round(report.decision.score, 4),
                "risk_veto": bool(report.decision.risk_vetoed_by),
                "target_weights": {
                    key: round(value, 4) for key, value in portfolio.plan.allocation.weights.items()
                },
                "portfolio_approved": portfolio.approved,
                "audit_valid": report.audit_receipt.chain_valid,
            }
        )


def make_fundamentals():
    retrieved_at = datetime(2025, 1, 1, tzinfo=UTC)

    def annual(year, revenue, ebit, available_at):
        return FundamentalSnapshot(
            symbol="ACME",
            period_start=date(year, 1, 1),
            period_end=date(year, 12, 31),
            filing_type="10-K",
            currency="USD",
            revenue=revenue,
            ebit=ebit,
            operating_cash_flow=35.0,
            capital_expenditure=5.0,
            cash_and_equivalents=15.0,
            total_debt=20.0,
            diluted_shares=10.0,
            net_income=16.0,
            pretax_income=21.0,
            income_tax_expense=4.4,
            interest_expense=1.0,
            total_equity=90.0,
            total_assets=140.0,
            provenance=DataProvenance(
                source="synthetic-fundamentals",
                retrieved_at=retrieved_at,
                available_at=available_at,
                metadata={"company_sic": "3571"},
            ),
            period_basis="fiscal-year",
        )

    return (
        annual(2023, 108.0, 22.0, datetime(2024, 2, 1, tzinfo=UTC)),
        annual(2022, 100.0, 20.0, datetime(2023, 2, 1, tzinfo=UTC)),
    )


if __name__ == "__main__":
    main()
