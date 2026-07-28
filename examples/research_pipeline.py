from datetime import UTC, datetime

from investement.backtesting import BacktestConfig, run_weight_backtest
from investement.domain import SignalAction
from investement.orchestration import (
    AgentFinding,
    EvidenceReference,
    InvestmentCommittee,
)
from investement.portfolio import (
    PortfolioConstraints,
    PortfolioRequest,
    RobustPortfolioOptimizer,
)
from investement.valuation import DCFInputs, discounted_cash_flow, valuation_signal


def main() -> None:
    dcf = discounted_cash_flow(
        DCFInputs(
            projected_free_cash_flows=(12.0, 13.0, 14.0, 15.0, 16.0),
            discount_rate=0.10,
            terminal_growth_rate=0.02,
            net_debt=10.0,
            diluted_shares=5.0,
        )
    )
    signal = valuation_signal(20.0, dcf.value_per_share, confidence=0.75)
    evidence = EvidenceReference(
        source="example-dcf",
        reference="run://example/base-case",
        observed_at=datetime.now(UTC),
    )
    decision = InvestmentCommittee().decide(
        (
            AgentFinding(
                agent="fundamental",
                subject="A",
                score=0.80 if signal.action == SignalAction.BUY else 0.0,
                confidence=signal.confidence,
                thesis="The base-case DCF offers a margin of safety.",
                evidence=(evidence,),
            ),
            AgentFinding(
                agent="risk",
                subject="A",
                score=0.20,
                confidence=0.80,
                thesis="No deterministic portfolio limit is breached.",
                evidence=(evidence,),
            ),
        )
    )
    allocation = RobustPortfolioOptimizer().optimize(
        PortfolioRequest(
            returns={
                "A": (0.010, 0.020, -0.010, 0.010),
                "B": (0.000, 0.005, 0.001, 0.002),
                "C": (0.002, -0.001, 0.003, 0.001),
            },
            constraints=PortfolioConstraints(max_weight=0.50, min_cash=0.10),
        )
    )
    target = allocation.weights["A"] if decision.action == SignalAction.BUY else 0.0
    backtest = run_weight_backtest(
        prices={"A": (100.0, 101.0, 103.0, 102.0)},
        target_weights={"A": (target, target, target, target)},
        config=BacktestConfig(commission_bps=1, slippage_bps=4),
    )
    print(
        {
            "fair_value": round(dcf.value_per_share, 2),
            "action": decision.action.value,
            "target_weight": round(target, 4),
            "backtest_total_return": round(backtest.metrics.total_return, 4),
        }
    )


if __name__ == "__main__":
    main()
