import unittest
from datetime import date, timedelta

from investement.portfolio import (
    AssetMetadata,
    PortfolioConstraints,
    PortfolioRequest,
    RobustPortfolioOptimizer,
)


class PortfolioTests(unittest.TestCase):
    def test_optimizer_projects_onto_asset_sector_country_and_cash_limits(self):
        request = PortfolioRequest(
            returns={
                "A": (0.01, 0.02, -0.01, 0.01),
                "B": (0.02, -0.01, 0.02, 0.00),
                "C": (0.00, 0.01, 0.00, 0.01),
                "D": (-0.01, 0.01, 0.02, 0.01),
            },
            constraints=PortfolioConstraints(
                max_weight=0.40,
                min_cash=0.10,
                sector_max_weights={"tech": 0.50},
                country_max_weights={"US": 0.70},
            ),
            metadata={
                "A": AssetMetadata(sector="tech", country="US"),
                "B": AssetMetadata(sector="tech", country="US"),
                "C": AssetMetadata(sector="bonds", country="US"),
                "D": AssetMetadata(sector="gold", country="global"),
            },
        )
        result = RobustPortfolioOptimizer().optimize(request)
        self.assertAlmostEqual(sum(result.weights.values()), 0.90)
        self.assertTrue(all(weight <= 0.40 + 1e-9 for weight in result.weights.values()))
        self.assertLessEqual(result.weights["A"] + result.weights["B"], 0.50 + 1e-9)
        self.assertLessEqual(
            result.weights["A"] + result.weights["B"] + result.weights["C"],
            0.70 + 1e-9,
        )
        self.assertEqual(result.backend, "inverse_volatility")

    def test_infeasible_caps_fail_loudly(self):
        request = PortfolioRequest(
            returns={"A": (0.01, 0.02), "B": (0.01, 0.02)},
            constraints=PortfolioConstraints(max_weight=0.30),
        )
        with self.assertRaises(ValueError):
            RobustPortfolioOptimizer().optimize(request)

    def test_volatility_limit_scales_risky_assets_into_cash_and_reports_tail_risk(self):
        request = PortfolioRequest(
            returns={
                "A": (0.08, -0.09, 0.07, -0.08, 0.06, -0.07),
                "B": (0.07, -0.08, 0.06, -0.07, 0.05, -0.06),
            },
            constraints=PortfolioConstraints(
                max_weight=0.70,
                min_cash=0.05,
                max_annual_volatility=0.20,
            ),
        )

        result = RobustPortfolioOptimizer().optimize(request)

        self.assertLessEqual(result.annual_volatility, 0.20 + 1e-10)
        self.assertGreater(result.cash_weight, 0.05)
        self.assertGreaterEqual(
            result.historical_expected_shortfall_95,
            result.historical_var_95,
        )
        self.assertGreater(result.effective_number_of_assets, 1)
        self.assertIn("scaled into cash", " ".join(result.warnings))

    def test_asset_class_and_currency_caps_are_enforced_and_reported(self):
        request = PortfolioRequest(
            returns={
                "A": (0.01, 0.02, -0.01, 0.01),
                "B": (0.02, -0.01, 0.02, 0.00),
                "C": (0.00, 0.01, 0.00, 0.01),
            },
            constraints=PortfolioConstraints(
                max_weight=0.60,
                min_cash=0.10,
                asset_class_max_weights={"equity": 0.50},
                currency_max_weights={"usd": 0.70},
            ),
            metadata={
                "A": AssetMetadata(asset_class="equity", currency="usd"),
                "B": AssetMetadata(asset_class="equity", currency="usd"),
                "C": AssetMetadata(asset_class="bond", currency="eur"),
            },
        )

        result = RobustPortfolioOptimizer().optimize(request)

        self.assertLessEqual(result.group_exposures["asset_class"]["equity"], 0.50 + 1e-9)
        self.assertLessEqual(result.group_exposures["currency"]["usd"], 0.70 + 1e-9)

    def test_return_calendar_is_validated_and_removes_alignment_warning(self):
        dates = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(4))
        request = PortfolioRequest(
            returns={
                "A": (0.01, 0.02, -0.01, 0.01),
                "B": (0.00, 0.01, 0.00, 0.01),
            },
            constraints=PortfolioConstraints(max_weight=0.60, min_cash=0.10),
            return_dates=dates,
        )

        result = RobustPortfolioOptimizer().optimize(request)

        self.assertFalse(any("alignment" in warning for warning in result.warnings))
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            PortfolioRequest(
                returns=request.returns,
                constraints=request.constraints,
                return_dates=(dates[0], dates[1], dates[1], dates[3]),
            )


if __name__ == "__main__":
    unittest.main()
