import unittest
from datetime import UTC, datetime, timedelta
from math import sin

from investement.agents import (
    AssetDataSnapshot,
    TechnicalAgent,
    TechnicalParameters,
    TechnicalRegime,
    TechnicalTimingAction,
)
from investement.agents.technical import _rsi_series
from investement.domain import DataProvenance, PriceBar
from investement.orchestration import EvidenceReference


class TechnicalAgentTests(unittest.TestCase):
    def test_baseline_parameters_and_required_history_are_explicit(self):
        parameters = TechnicalParameters()

        self.assertEqual(parameters.minimum_bars, 253)
        self.assertEqual(parameters.short_window, 50)
        self.assertEqual(parameters.long_window, 200)
        self.assertEqual(parameters.momentum_window, 252)
        self.assertEqual(parameters.momentum_skip, 21)
        self.assertEqual(parameters.rsi_window, 14)
        self.assertEqual(
            (parameters.macd_fast, parameters.macd_slow, parameters.macd_signal),
            (12, 26, 9),
        )

    def test_rsi_uses_wilders_recursive_smoothing(self):
        closes = (
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
        )

        rsi = _rsi_series(closes, 14)

        self.assertAlmostEqual(rsi[14], 70.4641, places=3)

    def test_bullish_breakout_favors_entry_on_the_next_bar_only(self):
        analysis = TechnicalAgent().analyze(_trend_snapshot(direction=1))

        self.assertEqual(analysis.trend_regime, TechnicalRegime.BULLISH)
        self.assertEqual(analysis.timing.action, TechnicalTimingAction.FAVOR_ENTRY)
        self.assertGreater(analysis.timing.strength, 0)
        self.assertTrue(analysis.timing.execute_on_next_bar)
        self.assertEqual(analysis.timing.valid_for_bars, 5)
        self.assertEqual(
            analysis.timing.observed_at,
            _trend_snapshot(direction=1).bars[-1].provenance.available_at,
        )
        self.assertIn("breakout", " ".join(analysis.timing.reasons).casefold())

    def test_confirmed_bearish_regime_favors_long_only_exit(self):
        analysis = TechnicalAgent().analyze(_trend_snapshot(direction=-1))

        self.assertEqual(analysis.trend_regime, TechnicalRegime.BEARISH)
        self.assertEqual(analysis.timing.action, TechnicalTimingAction.FAVOR_EXIT)
        self.assertLess(analysis.timing.strength, 0)
        self.assertGreaterEqual(len(analysis.timing.reasons), 2)

    def test_rejects_history_that_cannot_support_the_longest_indicator(self):
        snapshot = _trend_snapshot(direction=1, count=252, force_breakout=False)

        with self.assertRaisesRegex(ValueError, "at least 253 daily bars"):
            TechnicalAgent().analyze(snapshot)

    def test_rejects_non_daily_input_before_scoring(self):
        snapshot = _trend_snapshot(direction=1, interval="1h")

        with self.assertRaisesRegex(ValueError, "require daily bars"):
            TechnicalAgent().analyze(snapshot)


def _trend_snapshot(
    direction: int,
    count: int = 260,
    force_breakout: bool = True,
    interval: str = "1d",
) -> AssetDataSnapshot:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    closes = [100 + direction * 0.08 * index + 2 * sin(index * 0.4) for index in range(count)]
    if force_breakout and count >= 64:
        if direction > 0:
            closes[-1] = max(closes[-64:-1]) * 1.01
        else:
            closes[-1] = min(closes[-64:-1]) * 0.99

    bars = []
    for index, close in enumerate(closes):
        timestamp = start + timedelta(days=index)
        provenance = DataProvenance(
            source="technical-fixture",
            retrieved_at=timestamp,
            available_at=timestamp,
            raw_reference=f"fixture://TECH/{timestamp.date().isoformat()}",
            metadata={"interval": interval},
        )
        bars.append(
            PriceBar(
                symbol="TECH",
                timestamp=timestamp,
                open=close - 0.20,
                high=close + 0.50,
                low=close - 0.50,
                close=close,
                adjusted_close=close,
                volume=1_500_000 if index == count - 1 else 1_000_000,
                currency="USD",
                provenance=provenance,
            )
        )
    evidence = EvidenceReference(
        source="technical-fixture",
        reference="fixture://TECH",
        observed_at=bars[-1].provenance.available_at,
    )
    return AssetDataSnapshot(
        symbol="TECH",
        as_of=bars[-1].timestamp,
        retrieved_at=bars[-1].timestamp,
        bars=tuple(bars),
        filings=(),
        evidence=(evidence,),
    )


if __name__ == "__main__":
    unittest.main()
