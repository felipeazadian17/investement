import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from investement.data.protocols import MarketDataProvider
from investement.domain import DataProvenance, PriceBar


class JsonPriceBarCache:
    def __init__(self, root: Path, ttl: timedelta = timedelta(hours=12)) -> None:
        if ttl <= timedelta(0):
            raise ValueError("cache ttl must be positive")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl

    def load(self, key: str, now: datetime) -> tuple[PriceBar, ...] | None:
        path = self._path(key)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        saved_at = datetime.fromisoformat(payload["saved_at"])
        if now - saved_at > self.ttl:
            return None
        return tuple(_decode_bar(item) for item in payload["bars"])

    def save(self, key: str, bars: tuple[PriceBar, ...], now: datetime) -> None:
        path = self._path(key)
        payload = {
            "saved_at": now.isoformat(),
            "bars": [_encode_bar(bar) for bar in bars],
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=path.stem + ".", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"), default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"


class CachedMarketDataProvider:
    def __init__(
        self,
        provider: MarketDataProvider,
        cache: JsonPriceBarCache,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._clock = clock
        self.name = f"cached:{provider.name}"

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> tuple[PriceBar, ...]:
        key = (
            f"{self._provider.name}|{symbol.upper()}|{start.isoformat()}|"
            f"{end.isoformat()}|{interval}"
        )
        now = self._clock()
        cached = self._cache.load(key, now)
        if cached is not None:
            return cached
        bars = tuple(self._provider.history(symbol, start, end, interval))
        self._cache.save(key, bars, now)
        return bars

    def latest_quote(self, symbol: str):
        """Delegate live quotes without caching them as historical bars."""
        latest_quote = getattr(self._provider, "latest_quote", None)
        if latest_quote is None:
            raise RuntimeError(f"provider {self._provider.name} does not expose live quotes")
        return latest_quote(symbol)


def _encode_bar(bar: PriceBar) -> dict:
    return {
        "symbol": bar.symbol,
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "adjusted_close": bar.adjusted_close,
        "volume": bar.volume,
        "currency": bar.currency,
        "provenance": {
            "source": bar.provenance.source,
            "retrieved_at": bar.provenance.retrieved_at.isoformat(),
            "available_at": bar.provenance.available_at.isoformat(),
            "raw_reference": bar.provenance.raw_reference,
            "adjustments": list(bar.provenance.adjustments),
            "metadata": dict(bar.provenance.metadata),
        },
    }


def _decode_bar(payload: dict) -> PriceBar:
    provenance = payload["provenance"]
    return PriceBar(
        symbol=payload["symbol"],
        timestamp=datetime.fromisoformat(payload["timestamp"]),
        open=float(payload["open"]),
        high=float(payload["high"]),
        low=float(payload["low"]),
        close=float(payload["close"]),
        adjusted_close=float(payload["adjusted_close"]),
        volume=float(payload["volume"]),
        currency=payload["currency"],
        provenance=DataProvenance(
            source=provenance["source"],
            retrieved_at=datetime.fromisoformat(provenance["retrieved_at"]),
            available_at=datetime.fromisoformat(provenance["available_at"]),
            raw_reference=provenance["raw_reference"],
            adjustments=tuple(provenance["adjustments"]),
            metadata=provenance["metadata"],
        ),
    )
