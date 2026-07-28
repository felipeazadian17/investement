import unittest

from investement.backtesting import BacktestConfig, calculate_metrics, run_weight_backtest


class BacktestingTests(unittest.TestCase):
    def test_signal_is_shifted_and_cannot_capture_same_bar_jump(self):
        result = run_weight_backtest(
            prices={"A": (100.0, 200.0, 200.0)},
            target_weights={"A": (0.0, 1.0, 0.0)},
            config=BacktestConfig(commission_bps=0, slippage_bps=0, signal_delay_bars=1),
        )
        self.assertEqual(result.equity_curve[-1], 1.0)

    def test_costs_reduce_equity_and_are_reported(self):
        no_cost = run_weight_backtest(
            prices={"A": (100.0, 100.0, 110.0)},
            target_weights={"A": (1.0, 1.0, 1.0)},
            config=BacktestConfig(commission_bps=0, slippage_bps=0),
        )
        with_cost = run_weight_backtest(
            prices={"A": (100.0, 100.0, 110.0)},
            target_weights={"A": (1.0, 1.0, 1.0)},
            config=BacktestConfig(commission_bps=5, slippage_bps=5),
        )
        self.assertLess(with_cost.equity_curve[-1], no_cost.equity_curve[-1])
        self.assertGreater(with_cost.transaction_cost, 0)

    def test_zero_delay_is_rejected(self):
        with self.assertRaises(ValueError):
            BacktestConfig(signal_delay_bars=0)

    def test_metrics_capture_drawdown(self):
        metrics = calculate_metrics((0.10, -0.20, 0.05), periods_per_year=3)
        self.assertAlmostEqual(metrics.max_drawdown, -0.20)
        self.assertEqual(metrics.observations, 3)


if __name__ == "__main__":
    unittest.main()
