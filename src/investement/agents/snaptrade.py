from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from investement.agents.models import BrokerAccountSnapshot, BrokerPortfolioState
from investement.brokers.snaptrade_personal import ReadOnlySnapTradeClient
from investement.data import normalize_symbol

SUPPORTED_POSITION_KINDS = frozenset({"adr", "cef", "crypto", "etf", "mutualfund", "stock"})


class SnapTradeBrokerAgent:
    """Read-only broker agent for a SnapTrade Personal connection."""

    name = "snaptrade-personal-read-only"

    def __init__(
        self,
        client: ReadOnlySnapTradeClient,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock

    def read_portfolio(self, include_positions: bool = True) -> BrokerAccountSnapshot:
        retrieved_at = self._retrieved_at()
        accounts = tuple(self._client.portfolio(include_positions=include_positions))
        return BrokerAccountSnapshot(
            retrieved_at=retrieved_at,
            account_numbers=(),
            accounts=accounts,
        )

    def current_portfolio(self, base_currency: str = "USD") -> BrokerPortfolioState:
        retrieved_at = self._retrieved_at()
        currency = base_currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("base_currency must be a three-letter currency code")
        accounts = tuple(self._client.portfolio(include_positions=True))
        cash = Decimal(0)
        positions: dict[str, Decimal] = {}
        reported_totals: list[Decimal] = []
        for entry in accounts:
            account = entry["account"]
            account_total = account.get("balance", {}).get("total", {})
            amount = account_total.get("amount")
            if amount is not None:
                _require_currency(account_total.get("currency"), currency, "account total")
                reported_totals.append(_decimal(amount, "account total"))
            for balance in entry["balances"]:
                _require_currency(balance.get("currency"), currency, "cash balance")
                cash += _decimal(balance.get("cash", 0), "cash balance")
            for position in entry["positions"]:
                if position.get("cash_equivalent") is True:
                    continue
                instrument = position.get("instrument")
                if not isinstance(instrument, Mapping):
                    raise TypeError("SnapTrade position is missing instrument data")
                kind = str(instrument.get("kind", "")).strip().casefold()
                if kind not in SUPPORTED_POSITION_KINDS:
                    raise ValueError(
                        f"SnapTrade position kind {kind or 'unknown'} requires a dedicated valuator"
                    )
                raw_symbol = str(instrument.get("symbol", "")).strip()
                if not raw_symbol:
                    raise ValueError("SnapTrade position is missing a symbol")
                _require_currency(
                    position.get("currency") or instrument.get("currency"),
                    currency,
                    f"position {raw_symbol}",
                )
                units = _decimal(position.get("units"), f"units for {raw_symbol}")
                price = _decimal(position.get("price"), f"price for {raw_symbol}")
                value = units * price
                if value < 0:
                    raise ValueError("short broker positions are not supported")
                symbol = normalize_symbol(raw_symbol)
                positions[symbol] = positions.get(symbol, Decimal(0)) + value

        calculated_total = cash + sum(positions.values(), Decimal(0))
        total = sum(reported_totals, Decimal(0)) if len(reported_totals) == len(accounts) else calculated_total
        if total <= 0:
            raise ValueError("SnapTrade portfolio total must be positive")
        tolerance = max(Decimal("0.01"), total * Decimal("0.000001"))
        if calculated_total > total + tolerance:
            raise ValueError("SnapTrade positions and cash exceed the reported account total")
        return BrokerPortfolioState(
            retrieved_at=retrieved_at,
            provider=self.name,
            base_currency=currency,
            total_value=float(total),
            cash_value=float(cash),
            cash_weight=float(cash / total),
            position_values={symbol: float(value) for symbol, value in sorted(positions.items())},
            current_weights={symbol: float(value / total) for symbol, value in sorted(positions.items())},
        )

    def _retrieved_at(self) -> datetime:
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("SnapTrade agent clock must return a timezone-aware datetime")
        return retrieved_at


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"SnapTrade {label} is not numeric") from exc
    if not result.is_finite():
        raise ValueError(f"SnapTrade {label} must be finite")
    return result


def _require_currency(value: Any, expected: str, label: str) -> None:
    if isinstance(value, Mapping):
        value = value.get("code")
    actual = str(value or "").strip().upper()
    if not actual:
        raise ValueError(f"SnapTrade {label} is missing currency")
    if actual != expected:
        raise ValueError(
            f"SnapTrade {label} uses {actual}; FX conversion to {expected} is not configured"
        )
