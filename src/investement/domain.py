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


class CorporateActionKind(str, Enum):
    DIVIDEND = "dividend"
    CAPITAL_GAIN = "capital_gain"
    SPLIT = "split"


class InstrumentType(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    OPTION = "option"
    UNKNOWN = "unknown"


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
    period_start: date | None = None
    period_basis: str | None = None

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
        if self.period_start is not None and self.period_start > self.period_end:
            raise ValueError("period_start cannot be after period_end")

    @property
    def free_cash_flow(self) -> float | None:
        if self.operating_cash_flow is None or self.capital_expenditure is None:
            return None
        return self.operating_cash_flow - self.capital_expenditure


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    effective_at: datetime
    kind: CorporateActionKind
    value: float
    currency: str | None
    provenance: DataProvenance

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        require_aware(self.effective_at, "effective_at")
        require_finite(self.value, "value")
        if self.value <= 0:
            raise ValueError("corporate action value must be positive")


@dataclass(frozen=True)
class FundHolding:
    symbol: str | None
    name: str
    weight: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("holding name cannot be empty")
        require_finite(self.weight, "weight")
        if not 0 <= self.weight <= 1:
            raise ValueError("holding weight must be between zero and one")


@dataclass(frozen=True)
class FundSnapshot:
    symbol: str
    instrument_type: InstrumentType
    description: str | None
    category: str | None
    family: str | None
    expense_ratio: float | None
    net_assets: float | None
    asset_classes: Mapping[str, float]
    sector_weights: Mapping[str, float]
    top_holdings: tuple[FundHolding, ...]
    provenance: DataProvenance

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.instrument_type not in (InstrumentType.ETF, InstrumentType.MUTUAL_FUND):
            raise ValueError("fund snapshot requires an ETF or mutual fund")
        for name, value in (
            ("expense_ratio", self.expense_ratio),
            ("net_assets", self.net_assets),
        ):
            if value is not None:
                require_finite(value, name)
                if value < 0:
                    raise ValueError(f"{name} cannot be negative")
        for weights in (self.asset_classes, self.sector_weights):
            if any(not isfinite(value) or value < 0 for value in weights.values()):
                raise ValueError("fund weights must be finite and non-negative")


@dataclass(frozen=True)
class OptionContractSnapshot:
    contract_symbol: str
    underlying_symbol: str
    expiration: date
    option_type: str
    strike: float
    bid: float | None
    ask: float | None
    last_price: float | None
    implied_volatility: float | None
    open_interest: float | None
    volume: float | None
    in_the_money: bool | None
    last_trade_at: datetime | None
    currency: str | None
    contract_size: str | None

    def __post_init__(self) -> None:
        if not self.contract_symbol.strip() or not self.underlying_symbol.strip():
            raise ValueError("option symbols cannot be empty")
        if self.option_type not in ("call", "put"):
            raise ValueError("option_type must be call or put")
        require_finite(self.strike, "strike")
        if self.strike <= 0:
            raise ValueError("strike must be positive")
        for name in (
            "bid",
            "ask",
            "last_price",
            "implied_volatility",
            "open_interest",
            "volume",
        ):
            value = getattr(self, name)
            if value is not None:
                require_finite(value, name)
                if value < 0:
                    raise ValueError(f"{name} cannot be negative")
        if self.last_trade_at is not None:
            require_aware(self.last_trade_at, "last_trade_at")


@dataclass(frozen=True)
class OptionChainSnapshot:
    underlying_symbol: str
    expiration: date
    contracts: tuple[OptionContractSnapshot, ...]
    provenance: DataProvenance

    def __post_init__(self) -> None:
        if not self.underlying_symbol.strip() or not self.contracts:
            raise ValueError("option chain requires an underlying and contracts")
        if any(contract.expiration != self.expiration for contract in self.contracts):
            raise ValueError("option contracts must match the chain expiration")


@dataclass(frozen=True)
class MarketDataDiscrepancy:
    timestamp: datetime
    primary_close: float
    secondary_close: float
    relative_difference: float


@dataclass(frozen=True)
class MarketDataReconciliation:
    primary_source: str
    secondary_source: str
    overlap_count: int
    max_relative_difference: float
    discrepancies: tuple[MarketDataDiscrepancy, ...]
    checked_at: datetime

    def __post_init__(self) -> None:
        if not self.primary_source.strip() or not self.secondary_source.strip():
            raise ValueError("reconciliation sources cannot be empty")
        if self.overlap_count < 0:
            raise ValueError("overlap_count cannot be negative")
        require_finite(self.max_relative_difference, "max_relative_difference")
        require_aware(self.checked_at, "checked_at")
