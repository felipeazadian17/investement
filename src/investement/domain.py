from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from math import isfinite
from typing import Any


class SignalAction(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    REDUCE = "reduce"
    SELL = "sell"


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def require_finite(value: float, field_name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


@dataclass(frozen=True)
class DataProvenance:
    source: str
    retrieved_at: datetime
    available_at: datetime
    raw_reference: str | None = None
    adjustments: tuple = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source cannot be empty")
        require_aware(self.retrieved_at, "retrieved_at")
        require_aware(self.available_at, "available_at")
        if self.available_at > self.retrieved_at:
            raise ValueError("available_at cannot be later than retrieved_at")


@dataclass(frozen=True)
class PriceBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float
    currency: str | None
    provenance: DataProvenance

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        require_aware(self.timestamp, "timestamp")
        for name in ("open", "high", "low", "close", "adjusted_close", "volume"):
            require_finite(float(getattr(self, name)), name)
        if min(self.open, self.high, self.low, self.close, self.adjusted_close) <= 0:
            raise ValueError("prices must be positive")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is inconsistent with OHLC values")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is inconsistent with OHLC values")


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    period_end: date
    filing_type: str
    currency: str
    revenue: float | None
    ebit: float | None
    operating_cash_flow: float | None
    capital_expenditure: float | None
    cash_and_equivalents: float | None
    total_debt: float | None
    diluted_shares: float | None
    provenance: DataProvenance

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if not self.filing_type.strip():
            raise ValueError("filing_type cannot be empty")
        for name in (
            "revenue",
            "ebit",
            "operating_cash_flow",
            "capital_expenditure",
            "cash_and_equivalents",
            "total_debt",
            "diluted_shares",
        ):
            value = getattr(self, name)
            if value is not None:
                require_finite(float(value), name)
        if self.diluted_shares is not None and self.diluted_shares <= 0:
            raise ValueError("diluted_shares must be positive")
