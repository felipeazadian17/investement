from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Any

from investement.data.normalize import normalize_symbol, scalar, to_utc_datetime
from investement.domain import (
    DataProvenance,
    FundHolding,
    FundSnapshot,
    InstrumentType,
    OptionChainSnapshot,
    OptionContractSnapshot,
    PriceBar,
    require_aware,
)


class YFinanceProvider:
    """Thin, normalized adapter around yfinance.

    The downloader is injectable so normalization can be tested without network access.
    """

    name = "yfinance"

    def __init__(
        self,
        downloader: Callable[..., Any] | None = None,
        ticker_factory: Callable[[str], Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._downloader = downloader
        self._ticker_factory = ticker_factory
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

    def _ticker(self, symbol: str) -> Any:
        if self._ticker_factory is not None:
            return self._ticker_factory(symbol)
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is optional; install with `pip install -e '.[data]'`"
            ) from exc
        return yf.Ticker(symbol)

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
            end=(end + timedelta(days=1)).isoformat(),
            interval=interval,
            auto_adjust=False,
            actions=True,
            progress=False,
            group_by="column",
            multi_level_index=False,
        )
        if frame is None or getattr(frame, "empty", False):
            return []

        bars = []
        total_return_index = None
        previous_close = None
        rows = sorted(frame.iterrows(), key=lambda item: to_utc_datetime(item[0]))
        for index, row in rows:
            timestamp = to_utc_datetime(index)
            available_at = _bar_available_at(timestamp, interval)
            if available_at > retrieved_at:
                continue
            close = scalar(row, "Close", "close")
            dividend = _optional_scalar(row, "Dividends", "Dividend", "dividend")
            capital_gain = _optional_scalar(
                row,
                "Capital Gains",
                "Capital Gain",
                "capital_gain",
            )
            stock_split = _optional_scalar(row, "Stock Splits", "Stock Split", "stock_split")
            yahoo_adjusted_close = _optional_scalar(
                row,
                "Adj Close",
                "Adjusted Close",
                "adjusted_close",
            )
            if total_return_index is None or previous_close is None:
                total_return_index = close
            else:
                total_return_index *= (close + dividend + capital_gain) / previous_close
            provenance = DataProvenance(
                source=self.name,
                retrieved_at=retrieved_at,
                available_at=available_at,
                raw_reference=f"https://finance.yahoo.com/quote/{normalized}",
                adjustments=(
                    "auto_adjust=False",
                    "causal-total-return-index",
                    "yahoo-close-split-normalized",
                ),
                metadata={
                    "requested_symbol": symbol,
                    "interval": interval,
                    "dividend": dividend,
                    "capital_gain": capital_gain,
                    "stock_split": stock_split,
                    "yahoo_adjusted_close_ignored": yahoo_adjusted_close,
                },
            )
            bars.append(
                PriceBar(
                    symbol=normalized,
                    timestamp=timestamp,
                    open=scalar(row, "Open", "open"),
                    high=scalar(row, "High", "high"),
                    low=scalar(row, "Low", "low"),
                    close=close,
                    adjusted_close=total_return_index,
                    volume=scalar(row, "Volume", "volume"),
                    currency=None,
                    provenance=provenance,
                )
            )
            previous_close = close
        return bars

    def fund_snapshot(self, symbol: str, as_of: datetime) -> FundSnapshot | None:
        normalized = normalize_symbol(symbol)
        retrieved_at = self._clock()
        available_at = _current_snapshot_available_at(as_of, retrieved_at)
        try:
            funds = self._ticker(normalized).funds_data
            quote_type_value = funds.quote_type
            if callable(quote_type_value):
                quote_type_value = quote_type_value()
            quote_type = str(quote_type_value or "").upper()
            overview = dict(funds.fund_overview or {})
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
        if quote_type == "ETF":
            instrument_type = InstrumentType.ETF
        elif quote_type in ("MUTUALFUND", "MUTUAL FUND"):
            instrument_type = InstrumentType.MUTUAL_FUND
        else:
            return None

        operations = getattr(funds, "fund_operations", None)
        expense_ratio = _operation_value(
            operations,
            normalized,
            "Annual Report Expense Ratio",
            "Expense Ratio",
        )
        net_assets = _operation_value(
            operations,
            normalized,
            "Net Assets",
            "Total Net Assets",
        )
        if net_assets is not None:
            net_assets *= 1_000_000.0
        asset_classes = _weight_mapping(getattr(funds, "asset_classes", None))
        sector_weights = _weight_mapping(getattr(funds, "sector_weightings", None))
        holdings = _fund_holdings(getattr(funds, "top_holdings", None))
        return FundSnapshot(
            symbol=normalized,
            instrument_type=instrument_type,
            description=_optional_text(getattr(funds, "description", None)),
            category=_mapping_text(overview, "categoryName", "category"),
            family=_mapping_text(overview, "family", "fundFamily"),
            expense_ratio=_fraction(expense_ratio),
            net_assets=net_assets,
            asset_classes=asset_classes,
            sector_weights=sector_weights,
            top_holdings=holdings,
            provenance=DataProvenance(
                source="yfinance-funds",
                retrieved_at=retrieved_at,
                available_at=available_at,
                raw_reference=f"https://finance.yahoo.com/quote/{normalized}/holdings",
                adjustments=(
                    "weights-normalized-to-fractions",
                    "net-assets-millions-to-units",
                ),
                metadata={"quote_type": quote_type, "current_snapshot_only": True},
            ),
        )

    def option_chain(
        self,
        symbol: str,
        expiration: date,
        as_of: datetime,
    ) -> OptionChainSnapshot:
        normalized = normalize_symbol(symbol)
        retrieved_at = self._clock()
        available_at = _current_snapshot_available_at(as_of, retrieved_at)
        ticker = self._ticker(normalized)
        expiration_text = expiration.isoformat()
        expirations = tuple(str(item) for item in ticker.options)
        if expiration_text not in expirations:
            raise ValueError(
                f"{expiration_text} is not an available option expiration for {normalized}"
            )
        chain = ticker.option_chain(expiration_text)
        contracts = []
        for option_type, frame in (("call", chain.calls), ("put", chain.puts)):
            for _, row in frame.iterrows():
                contracts.append(
                    _option_contract(normalized, expiration, option_type, row)
                )
        if not contracts:
            raise ValueError(f"no option contracts returned for {normalized} {expiration_text}")
        return OptionChainSnapshot(
            underlying_symbol=normalized,
            expiration=expiration,
            contracts=tuple(contracts),
            provenance=DataProvenance(
                source="yfinance-options",
                retrieved_at=retrieved_at,
                available_at=available_at,
                raw_reference=f"https://finance.yahoo.com/quote/{normalized}/options",
                metadata={
                    "expiration": expiration_text,
                    "current_snapshot_only": True,
                },
            ),
        )


def _optional_scalar(row: Any, *keys: str) -> float:
    try:
        value = scalar(row, *keys)
    except (KeyError, TypeError, ValueError):
        return 0.0
    return value if isfinite(value) else 0.0


def _current_snapshot_available_at(as_of: datetime, retrieved_at: datetime) -> datetime:
    require_aware(as_of, "as_of")
    require_aware(retrieved_at, "retrieved_at")
    if as_of.astimezone(UTC).date() != retrieved_at.astimezone(UTC).date():
        raise ValueError("Yahoo fund and option snapshots cannot satisfy a historical as_of")
    return min(as_of, retrieved_at)


def _operation_value(frame: Any, symbol: str, *labels: str) -> float | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    for label in labels:
        try:
            row = frame.loc[label]
        except (KeyError, TypeError):
            continue
        for key in (symbol, "Value", "value"):
            try:
                value = float(row[key])
            except (KeyError, TypeError, ValueError):
                continue
            if isfinite(value):
                return value
        try:
            value = float(row.iloc[0])
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
        if isfinite(value):
            return value
    return None


def _weight_mapping(values: Any) -> dict[str, float]:
    if values is None:
        return {}
    if hasattr(values, "to_dict"):
        values = values.to_dict()
    if not isinstance(values, dict):
        return {}
    result = {}
    for key, raw_value in values.items():
        try:
            value = _fraction(float(raw_value))
        except (TypeError, ValueError):
            continue
        if value is not None and isfinite(value) and value >= 0:
            result[str(key)] = value
    return result


def _fraction(value: float | None) -> float | None:
    if value is None or not isfinite(value) or value < 0:
        return None
    return value / 100.0 if value > 1.0 and value <= 100.0 else value


def _fund_holdings(frame: Any) -> tuple[FundHolding, ...]:
    if frame is None or getattr(frame, "empty", True):
        return ()
    holdings = []
    for index, row in frame.iterrows():
        name = _row_text(row, "Name", "Holding Name", "name") or str(index)
        symbol = _row_text(row, "Symbol", "symbol")
        if symbol is None and str(index).strip() and str(index) != name:
            symbol = str(index).strip()
        weight = _row_float(row, "Holding Percent", "holdingPercent", "Weight", "weight")
        weight = _fraction(weight)
        if weight is None or weight > 1:
            continue
        holdings.append(FundHolding(symbol=symbol, name=name, weight=weight))
    return tuple(holdings)


def _option_contract(
    underlying: str,
    expiration: date,
    option_type: str,
    row: Any,
) -> OptionContractSnapshot:
    contract_symbol = _row_text(row, "contractSymbol", "Contract Symbol")
    if contract_symbol is None:
        raise ValueError("option contract is missing contractSymbol")
    last_trade = _row_value(row, "lastTradeDate", "Last Trade Date")
    last_trade_at = None
    if last_trade is not None and str(last_trade) not in ("", "NaT", "nan"):
        last_trade_at = to_utc_datetime(last_trade)
    strike = _row_float(row, "strike", "Strike")
    if strike is None:
        raise ValueError(f"option contract {contract_symbol} is missing strike")
    return OptionContractSnapshot(
        contract_symbol=contract_symbol,
        underlying_symbol=underlying,
        expiration=expiration,
        option_type=option_type,
        strike=strike,
        bid=_row_float(row, "bid", "Bid"),
        ask=_row_float(row, "ask", "Ask"),
        last_price=_row_float(row, "lastPrice", "Last Price"),
        implied_volatility=_row_float(row, "impliedVolatility", "Implied Volatility"),
        open_interest=_row_float(row, "openInterest", "Open Interest"),
        volume=_row_float(row, "volume", "Volume"),
        in_the_money=_row_bool(row, "inTheMoney", "In The Money"),
        last_trade_at=last_trade_at,
        currency=_row_text(row, "currency", "Currency"),
        contract_size=_row_text(row, "contractSize", "Contract Size"),
    )


def _row_value(row: Any, *keys: str) -> Any:
    for key in keys:
        try:
            return row[key]
        except (KeyError, TypeError):
            continue
    return None


def _row_float(row: Any, *keys: str) -> float | None:
    value = _row_value(row, *keys)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and result >= 0 else None


def _row_text(row: Any, *keys: str) -> str | None:
    return _optional_text(_row_value(row, *keys))


def _row_bool(row: Any, *keys: str) -> bool | None:
    value = _row_value(row, *keys)
    return value if isinstance(value, bool) else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("nan", "none") else None


def _mapping_text(values: dict, *keys: str) -> str | None:
    for key in keys:
        value = _optional_text(values.get(key))
        if value is not None:
            return value
    return None


def _bar_available_at(timestamp: datetime, interval: str) -> datetime:
    cleaned = interval.strip().lower()
    if cleaned.endswith("m") and cleaned[:-1].isdigit():
        return timestamp + timedelta(minutes=int(cleaned[:-1]))
    if cleaned.endswith("h") and cleaned[:-1].isdigit():
        return timestamp + timedelta(hours=int(cleaned[:-1]))
    if cleaned.endswith("d") and cleaned[:-1].isdigit():
        return timestamp + timedelta(days=int(cleaned[:-1]))
    if cleaned.endswith("wk") and cleaned[:-2].isdigit():
        return timestamp + timedelta(weeks=int(cleaned[:-2]))
    if cleaned.endswith("mo") and cleaned[:-2].isdigit():
        return timestamp + timedelta(days=31 * int(cleaned[:-2]))
    raise ValueError(f"unsupported yfinance interval: {interval}")
