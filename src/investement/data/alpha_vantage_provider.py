import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from investement.data.normalize import normalize_symbol
from investement.domain import DataProvenance, PriceBar


class AlphaVantageProvider:
    """Normalized read-only adapter for Alpha Vantage daily OHLC data."""

    name = "alpha-vantage"
    endpoint = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: str,
        requester: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        outputsize: str = "compact",
    ) -> None:
        if not api_key.strip():
            raise ValueError("Alpha Vantage api_key cannot be empty")
        if outputsize not in ("compact", "full"):
            raise ValueError("outputsize must be compact or full")
        self._api_key = api_key.strip()
        self._requester = requester or _get_json
        self._clock = clock
        self._outputsize = outputsize

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> Sequence[PriceBar]:
        if interval != "1d":
            raise ValueError("Alpha Vantage provider currently supports only 1d bars")
        if end <= start:
            raise ValueError("end must be later than start")
        normalized = normalize_symbol(symbol)
        retrieved_at = self._clock()
        payload = self._requester(
            self.endpoint,
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": normalized,
                "outputsize": self._outputsize,
                "apikey": self._api_key,
            },
        )
        series = payload.get("Time Series (Daily)")
        try:
            series_items = series.items()
        except AttributeError as exc:
            message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
            raise RuntimeError(
                f"Alpha Vantage returned no daily series: {message or 'unknown error'}"
            ) from exc

        bars = []
        for day_text, values in sorted(series_items):
            day = date.fromisoformat(str(day_text))
            if day < start or day > end:
                continue
            timestamp = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
            available_at = timestamp + timedelta(days=1)
            if available_at > retrieved_at:
                continue
            if not isinstance(values, Mapping):
                continue
            bars.append(
                PriceBar(
                    symbol=normalized,
                    timestamp=timestamp,
                    open=_number(values, "1. open"),
                    high=_number(values, "2. high"),
                    low=_number(values, "3. low"),
                    close=_number(values, "4. close"),
                    adjusted_close=_number(values, "4. close"),
                    volume=_number(values, "5. volume"),
                    currency=None,
                    provenance=DataProvenance(
                        source=self.name,
                        retrieved_at=retrieved_at,
                        available_at=available_at,
                        raw_reference=(
                            "https://www.alphavantage.co/documentation/"
                            "#dailyadj"
                        ),
                        adjustments=("raw-close", "no-dividend-adjustment"),
                        metadata={
                            "requested_symbol": symbol,
                            "interval": interval,
                            "function": "TIME_SERIES_DAILY",
                        },
                    ),
                )
            )
        return bars


def _get_json(url: str, params: Mapping[str, str]) -> Mapping[str, Any]:
    request_url = f"{url}?{urlencode(params)}"
    with urlopen(request_url, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise TypeError("Alpha Vantage response must be a JSON object")
    return payload


def _number(values: Mapping[str, Any], key: str) -> float:
    try:
        result = float(values[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Alpha Vantage row is missing numeric field {key}") from exc
    if not isfinite(result):
        raise ValueError(f"Alpha Vantage field {key} must be finite")
    return result
