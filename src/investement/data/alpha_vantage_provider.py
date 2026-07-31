import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from investement.data.normalize import normalize_symbol
from investement.domain import DataProvenance, PriceBar, QuoteSnapshot


class AlphaVantageProvider:
    """Normalized read-only adapter for Alpha Vantage market data.

    Historical bars and live quotes are separate interfaces. Realtime US
    quotes require the provider's appropriate exchange entitlement, so the
    returned provenance is preserved for freshness checks.
    """

    name = "alpha-vantage"
    endpoint = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: str,
        requester: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        outputsize: str = "compact",
        adjusted: bool = False,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Alpha Vantage api_key cannot be empty")
        if outputsize not in ("compact", "full"):
            raise ValueError("outputsize must be compact or full")
        self._api_key = api_key.strip()
        self._requester = requester or _get_json
        self._clock = clock
        self._outputsize = outputsize
        self._adjusted = adjusted

    def latest_quote(self, symbol: str, entitlement: str = "realtime") -> QuoteSnapshot:
        if entitlement not in ("realtime", "delayed", ""):
            raise ValueError("entitlement must be realtime, delayed, or empty")
        normalized = normalize_symbol(symbol)
        retrieved_at = self._clock()
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": normalized,
            "apikey": self._api_key,
        }
        if entitlement:
            params["entitlement"] = entitlement
        payload = self._requester(self.endpoint, params)
        values = payload.get("Global Quote")
        if not isinstance(values, Mapping) or not values:
            message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
            raise RuntimeError(f"Alpha Vantage returned no quote: {message or 'unknown error'}")
        return QuoteSnapshot(
            symbol=normalized,
            last_price=_number(values, "05. price"),
            bid=_optional_number(values, "08. bid price"),
            ask=_optional_number(values, "09. ask price"),
            volume=_optional_number(values, "06. volume"),
            provenance=DataProvenance(
                source=self.name,
                retrieved_at=retrieved_at,
                available_at=retrieved_at,
                raw_reference="https://www.alphavantage.co/documentation/#latestprice",
                adjustments=("as-traded-quote",),
                metadata={
                    "function": "GLOBAL_QUOTE",
                    "entitlement": entitlement,
                    "latest_trading_day": values.get("07. latest trading day"),
                },
            ),
        )

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
        function = "TIME_SERIES_DAILY_ADJUSTED" if self._adjusted else "TIME_SERIES_DAILY"
        payload = self._requester(
            self.endpoint,
            {
                "function": function,
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
        total_return_index = None
        previous_close = None
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
            close = _number(values, "4. close")
            dividend = _optional_number(values, "7. dividend amount")
            split = _optional_number(values, "8. split coefficient") or 1.0
            if total_return_index is None or previous_close is None:
                total_return_index = close
            else:
                total_return_index *= (close * split + (dividend or 0.0)) / previous_close
            bars.append(
                PriceBar(
                    symbol=normalized,
                    timestamp=timestamp,
                    open=_number(values, "1. open"),
                    high=_number(values, "2. high"),
                    low=_number(values, "3. low"),
                    close=close,
                    adjusted_close=total_return_index,
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
                        adjustments=("causal-total-return-index", f"endpoint:{function}"),
                        metadata={
                            "requested_symbol": symbol,
                            "interval": interval,
                            "function": function,
                            "dividend": dividend,
                            "stock_split": split if split != 1.0 else 0.0,
                            "provider_adjusted_close_ignored": _optional_number(
                                values, "5. adjusted close"
                            ),
                        },
                    ),
                )
            )
            previous_close = close
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


def _optional_number(values: Mapping[str, Any], key: str) -> float | None:
    value = values.get(key)
    if value in (None, "", "None"):
        return None
    return _number(values, key)
