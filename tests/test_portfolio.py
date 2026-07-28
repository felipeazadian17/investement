import unittest

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


if __name__ == "__main__":
    unittest.main()
