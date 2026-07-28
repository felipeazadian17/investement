from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from investement.agents import (
    AssetAnalysisRequest,
    AssetDataRequest,
    AuditorAgent,
    DataAgent,
    FundamentalModelInputs,
    InvestmentAgentPipeline,
    InvestorProfileRequest,
    PortfolioConstructionInputs,
    RelativeValuationInputs,
    RiskTolerance,
)
from investement.domain import DataProvenance, PriceBar
from investement.orchestration import JsonlAuditLog, JsonMemoryStore
from investement.portfolio import AssetMetadata
from investement.valuation import ComparableObservation


class SyntheticMarketData:
    name = "synthetic-example"

    def __init__(self, bars):
        self._bars = bars

    def history(self, symbol, start, end, interval="1d"):
        return self._bars


def make_bars(count=90):
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
    with TemporaryDirectory() as directory:
        artifacts = Path(directory)
        pipeline = InvestmentAgentPipeline(
            DataAgent(
                SyntheticMarketData(bars),
                clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
            ),
            auditor=AuditorAgent(
                JsonlAuditLog(artifacts / "audit.jsonl"),
                JsonMemoryStore(artifacts / "memory"),
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
                fundamentals=FundamentalModelInputs(
                    base_free_cash_flow=30,
                    growth_rates=(0.08, 0.07, 0.06, 0.05, 0.04),
                    discount_rate=0.10,
                    terminal_growth_rate=0.025,
                    net_debt=20,
                    diluted_shares=10,
                    roic=0.17,
                    revenue_growth=0.08,
                    operating_margin=0.21,
                    debt_to_free_cash_flow=1.4,
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


if __name__ == "__main__":
    main()
