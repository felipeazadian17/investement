import unittest
from datetime import UTC, datetime, timedelta

from investement.backtesting import (
    RecommendationObservation,
    apply_cost_stress,
    evaluate_recommendations,
    summarize_walk_forward,
)
from investement.domain import DataProvenance, PriceBar, SignalAction


class WalkForwardValidationTests(unittest.TestCase):
    def test_monthly_evaluation_enters_after_the_signal_and_uses_total_return(self):
        cutoff = datetime(2024, 1, 31, 23, 59, tzinfo=UTC)
        bars = _bars("A", datetime(2024, 1, 30, tzinfo=UTC), (100.0, 101.0, 106.0))
        recommendation = RecommendationObservation(
            "A", cutoff, SignalAction.BUY, 0.7, 0.8, observed_price=100.0
        )

        outcome = evaluate_recommendations(
            (recommendation,),
            {"A": bars},
            datetime(2024, 3, 1, tzinfo=UTC),
            transaction_cost_bps=10,
        )[0]

        self.assertEqual(outcome.entry_price, 101.0)
        self.assertAlmostEqual(outcome.underlying_total_return, 106.0 / 101.0 - 1)
        self.assertAlmostEqual(outcome.directional_return, 106.0 / 101.0 - 1 - 0.001)

    def test_summary_and_cost_stress_keep_holds_out_of_directional_accuracy(self):
        cutoff = datetime(2024, 1, 31, 23, 59, tzinfo=UTC)
        recommendations = (
            RecommendationObservation("A", cutoff, SignalAction.BUY, 0.8, 0.8, 100.0),
            RecommendationObservation("B", cutoff, SignalAction.SELL, -0.8, 0.8, 100.0),
            RecommendationObservation("C", cutoff, SignalAction.HOLD, 0.0, 0.8, 100.0),
        )
        bars = {
            "A": _bars("A", datetime(2024, 1, 30, tzinfo=UTC), (100.0, 101.0, 110.0)),
            "B": _bars("B", datetime(2024, 1, 30, tzinfo=UTC), (100.0, 99.0, 90.0)),
            "C": _bars("C", datetime(2024, 1, 30, tzinfo=UTC), (100.0, 100.0, 101.0)),
        }
        outcomes = evaluate_recommendations(
            recommendations, bars, datetime(2024, 3, 1, tzinfo=UTC)
        )
        metrics = summarize_walk_forward(outcomes)
        stressed = summarize_walk_forward(apply_cost_stress(outcomes, 50))

        self.assertEqual(metrics.actionable, 2)
        self.assertEqual(metrics.holds, 1)
        self.assertEqual(metrics.hit_rate, 1.0)
        self.assertLess(stressed.mean_directional_return, metrics.mean_directional_return)


def _bars(symbol, start, prices):
    retrieved = datetime(2024, 4, 1, tzinfo=UTC)
    result = []
    for index, price in enumerate(prices):
        timestamp = start + timedelta(days=index)
        result.append(
            PriceBar(
                symbol=symbol,
                timestamp=timestamp,
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=price,
                volume=1_000.0,
                currency="USD",
                provenance=DataProvenance(
                    source="fixture",
                    retrieved_at=retrieved,
                    available_at=timestamp + timedelta(days=1),
                    metadata={"interval": "1d"},
                ),
            )
        )
    return tuple(result)


if __name__ == "__main__":
    unittest.main()
