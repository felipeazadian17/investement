from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from typing import Any

from investement.data.normalize import normalize_symbol, scalar, to_utc_datetime
from investement.domain import DataProvenance, PriceBar


class YFinanceProvider:
    """Thin, normalized adapter around yfinance.

    The downloader is injectable so normalization can be tested without network access.
    """

    name = "yfinance"

    def __init__(
        self,
        downloader: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._downloader = downloader
        self._clock = clock

    def _download(self, **kwargs: Any) -> Any:
        if self._downloader is not None:
            return self._downloader(**kwargs)
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is optional; install with `pip install -e '.[data]'`"
            ) from exc
        return yf.download(**kwargs)

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> Sequence[PriceBar]:
        if end <= start:
            raise ValueError("end must be later than start")
        normalized = normalize_symbol(symbol)
        retrieved_at = self._clock()
        frame = self._download(
            tickers=normalized,
            start=start.isoformat(),
            end=end.isoformat(),
            interval=interval,
            auto_adjust=False,
            actions=False,
            progress=False,
            group_by="column",
            multi_level_index=False,
        )
        if frame is None or getattr(frame, "empty", False):
            return []

        bars = []
        for index, row in frame.iterrows():
            timestamp = to_utc_datetime(index)
            close = scalar(row, "Close", "close")
            try:
                adjusted_close = scalar(row, "Adj Close", "Adjusted Close", "adjusted_close")
            except KeyError:
                adjusted_close = close
            provenance = DataProvenance(
                source=self.name,
                retrieved_at=retrieved_at,
                available_at=min(timestamp, retrieved_at),
                raw_reference=f"https://finance.yahoo.com/quote/{normalized}",
                adjustments=("auto_adjust=False",),
                metadata={"requested_symbol": symbol, "interval": interval},
            )
            bars.append(
                PriceBar(
                    symbol=normalized,
                    timestamp=timestamp,
                    open=scalar(row, "Open", "open"),
                    high=scalar(row, "High", "high"),
                    low=scalar(row, "Low", "low"),
                    close=close,
                    adjusted_close=adjusted_close,
                    volume=scalar(row, "Volume", "volume"),
                    currency=None,
                    provenance=provenance,
                )
            )
        return bars
