import unittest

from investement.portfolio import (
    MODEL_NAMES,
    AssetMetadata,
    PortfolioConstraints,
    build_candidate_weights,
    select_monthly_model,
)


class PortfolioTournamentTests(unittest.TestCase):
    def test_all_models_respect_shared_constraints(self):
        returns = _returns()
        metadata = _metadata(returns)
        candidates = build_candidate_weights(
            returns,
            PortfolioConstraints(max_weight=0.30, min_cash=0.10),
            metadata,
        )
        self.assertEqual(set(candidates), set(MODEL_NAMES))
        for weights in candidates.values():
            self.assertAlmostEqual(sum(weights.values()), 0.90)
            self.assertLessEqual(max(weights.values()), 0.30 + 1e-8)

    def test_selector_refits_selected_model_for_live_window(self):
        estimation = _returns(offset=0.0001)
        validation = _returns(offset=-0.0002)
        decision = select_monthly_model(
            estimation,
            validation,
            _returns(offset=0.0004),
            PortfolioConstraints(max_weight=0.30, min_cash=0.10),
            _metadata(estimation),
            previous_weights={asset: 0.18 for asset in estimation},
        )
        self.assertIn(decision.selected_model, MODEL_NAMES)
        self.assertEqual(len(decision.evaluations), len(MODEL_NAMES))
        self.assertAlmostEqual(sum(decision.selected_weights.values()), 0.90)


def _returns(offset=0.0):
    return {
        asset: tuple(
            offset + ((index % (position + 3)) - (position + 1)) / 10_000
            for index in range(180)
        )
        for position, asset in enumerate(("A", "B", "C", "D", "E"))
    }


def _metadata(returns):
    return {
        asset: AssetMetadata(asset_class="equity", country="us", currency="usd")
        for asset in returns
    }


if __name__ == "__main__":
    unittest.main()
