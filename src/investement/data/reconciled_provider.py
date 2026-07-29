from collections.abc import Sequence
from datetime import UTC, date, datetime

from investement.data.protocols import MarketDataProvider
from investement.domain import (
    MarketDataDiscrepancy,
    MarketDataReconciliation,
    PriceBar,
)


class MarketDataMismatchError(RuntimeError):
    pass


class ReconciledMarketDataProvider:
    """Returns primary bars and records close-price differences against a second source."""

    def __init__(
        self,
        primary: MarketDataProvider,
        secondary: MarketDataProvider,
        relative_tolerance: float = 0.01,
        comparison_window: int = 20,
        strict: bool = False,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        if relative_tolerance < 0:
            raise ValueError("relative_tolerance cannot be negative")
        if comparison_window <= 0:
            raise ValueError("comparison_window must be positive")
        self._primary = primary
        self._secondary = secondary
        self._relative_tolerance = relative_tolerance
        self._comparison_window = comparison_window
        self._strict = strict
        self._clock = clock
        self.name = f"reconciled:{primary.name}:{secondary.name}"
        self.last_reconciliation: MarketDataReconciliation | None = None

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> Sequence[PriceBar]:
        primary = tuple(self._primary.history(symbol, start, end, interval))
        secondary = tuple(self._secondary.history(symbol, start, end, interval))
        secondary_by_timestamp = {bar.timestamp: bar for bar in secondary}
        overlap = [
            (bar, secondary_by_timestamp[bar.timestamp])
            for bar in primary
            if bar.timestamp in secondary_by_timestamp
        ][-self._comparison_window :]
        if not overlap:
            raise MarketDataMismatchError(
                f"no overlapping bars between {self._primary.name} and {self._secondary.name}"
            )

        discrepancies = []
        maximum = 0.0
        for primary_bar, secondary_bar in overlap:
            difference = abs(primary_bar.close - secondary_bar.close) / max(
                abs(secondary_bar.close), 1e-12
            )
            maximum = max(maximum, difference)
            if difference > self._relative_tolerance:
                discrepancies.append(
                    MarketDataDiscrepancy(
                        timestamp=primary_bar.timestamp,
                        primary_close=primary_bar.close,
                        secondary_close=secondary_bar.close,
                        relative_difference=difference,
                    )
                )
        self.last_reconciliation = MarketDataReconciliation(
            primary_source=self._primary.name,
            secondary_source=self._secondary.name,
            overlap_count=len(overlap),
            max_relative_difference=maximum,
            discrepancies=tuple(discrepancies),
            checked_at=self._clock(),
        )
        if self._strict and discrepancies:
            raise MarketDataMismatchError(
                f"{len(discrepancies)} market bars exceed "
                f"{self._relative_tolerance:.2%} tolerance"
            )
        return primary
