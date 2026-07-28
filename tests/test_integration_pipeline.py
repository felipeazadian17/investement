import unittest
from datetime import UTC, datetime

from investement.backtesting import BacktestConfig, run_weight_backtest
from investement.domain import SignalAction
from investement.orchestration import AgentFinding, EvidenceReference, InvestmentCommittee
from investement.portfolio import PortfolioConstraints, PortfolioRequest, RobustPortfolioOptimizer
from investement.valuation import DCFInputs, discounted_cash_flow, valuation_signal


class IntegrationPipelineTests(unittest.TestCase):
    def test_valuation_committee_portfolio_and_backtest_share_structured_outputs(self):
        dcf = discounted_cash_flow(
            DCFInputs((12.0, 13.0, 14.0), 0.10, 0.02, net_debt=10.0, diluted_shares=5.0)
        )
        signal = valuation_signal(
            current_price=20.0,
            fair_value=dcf.value_per_share,
            confidence=0.75,
            required_margin=0.10,
        )
        evidence = EvidenceReference(
            source="dcf",
            reference="run://dcf/base",
            observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        committee = InvestmentCommittee().decide(
            (
                AgentFinding(
                    "fundamental",
                    "A",
                    0.8 if signal.action == SignalAction.BUY else 0.0,
                    signal.confidence,
                    "DCF with margin of safety",
                    (evidence,),
                ),
                AgentFinding("risk", "A", 0.2, 0.8, "No hard risk limit breached", (evidence,)),
            )
        )
        allocation = RobustPortfolioOptimizer().optimize(
            PortfolioRequest(
                returns={
                    "A": (0.01, 0.02, -0.01, 0.01),
                    "B": (0.00, 0.005, 0.001, 0.002),
                    "C": (0.002, -0.001, 0.003, 0.001),
                },
                constraints=PortfolioConstraints(max_weight=0.50, min_cash=0.10),
            )
        )
        target = allocation.weights["A"] if committee.action == SignalAction.BUY else 0.0
        backtest = run_weight_backtest(
            prices={"A": (100.0, 101.0, 103.0)},
            target_weights={"A": (target, target, target)},
            config=BacktestConfig(commission_bps=1, slippage_bps=2),
        )
        self.assertEqual(committee.action, SignalAction.BUY)
        self.assertGreater(target, 0)
        self.assertEqual(backtest.metrics.observations, 2)


if __name__ == "__main__":
    unittest.main()
