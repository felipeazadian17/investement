import unittest

from investement.domain import SignalAction
from investement.valuation import (
    ComparableObservation,
    DCFInputs,
    discounted_cash_flow,
    project_cash_flows,
    sensitivity_matrix,
    valuation_signal,
    value_from_comparables,
)


class ValuationTests(unittest.TestCase):
    def test_dcf_matches_explicit_formula(self):
        result = discounted_cash_flow(
            DCFInputs(
                projected_free_cash_flows=(100.0, 110.0),
                discount_rate=0.10,
                terminal_growth_rate=0.02,
                net_debt=50.0,
                diluted_shares=10.0,
            )
        )
        expected_interim = 100 / 1.1 + 110 / (1.1**2)
        expected_terminal = (110 * 1.02 / (0.10 - 0.02)) / (1.1**2)
        self.assertAlmostEqual(result.enterprise_value, expected_interim + expected_terminal)
        self.assertAlmostEqual(result.value_per_share, (result.enterprise_value - 50) / 10)
        self.assertGreater(result.terminal_value_share, 0.5)

    def test_dcf_rejects_non_economic_terminal_assumption(self):
        with self.assertRaises(ValueError):
            DCFInputs((100.0,), 0.03, 0.03, 0.0, 10.0)

    def test_projection_and_sensitivity_are_monotonic(self):
        projected = project_cash_flows(100.0, (0.10, 0.05))
        self.assertEqual(projected, (110.00000000000001, 115.50000000000001))
        matrix = sensitivity_matrix(projected, (0.08, 0.10), (0.02,), 0.0, 10.0)
        self.assertGreater(matrix[0.08][0.02], matrix[0.10][0.02])

    def test_comparables_use_robust_median_and_remove_outlier(self):
        observations = [
            ComparableObservation("A", 10.0, "PE"),
            ComparableObservation("B", 11.0, "PE"),
            ComparableObservation("C", 12.0, "PE"),
            ComparableObservation("D", 100.0, "PE"),
        ]
        result = value_from_comparables(2.0, observations, "pe")
        self.assertEqual(result.selected_multiple, 11.0)
        self.assertEqual(result.value_per_share, 22.0)
        self.assertEqual(result.excluded_outliers, ("D",))

    def test_margin_of_safety_drives_structured_action(self):
        buy = valuation_signal(70.0, 100.0, confidence=0.8)
        sell = valuation_signal(130.0, 100.0, confidence=0.8)
        self.assertEqual(buy.action, SignalAction.BUY)
        self.assertAlmostEqual(buy.margin_of_safety, 0.30)
        self.assertEqual(sell.action, SignalAction.SELL)


if __name__ == "__main__":
    unittest.main()
