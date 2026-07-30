from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class AssetMetadata:
    sector: str | None = None
    country: str | None = None
    asset_class: str | None = None
    currency: str | None = None


@dataclass(frozen=True)
class PortfolioConstraints:
    min_weight: float = 0.0
    max_weight: float = 0.25
    min_cash: float = 0.0
    asset_max_weights: Mapping[str, float] = field(default_factory=dict)
    sector_max_weights: Mapping[str, float] = field(default_factory=dict)
    country_max_weights: Mapping[str, float] = field(default_factory=dict)
    asset_class_max_weights: Mapping[str, float] = field(default_factory=dict)
    currency_max_weights: Mapping[str, float] = field(default_factory=dict)
    max_annual_volatility: float | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.min_weight, "min_weight"),
            (self.max_weight, "max_weight"),
            (self.min_cash, "min_cash"),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.min_weight > self.max_weight:
            raise ValueError("min_weight cannot exceed max_weight")
        for limits in (
            self.asset_max_weights,
            self.sector_max_weights,
            self.country_max_weights,
            self.asset_class_max_weights,
            self.currency_max_weights,
        ):
            if any(not isfinite(value) or not 0 <= value <= 1 for value in limits.values()):
                raise ValueError("all constraint limits must be between 0 and 1")
        if self.max_annual_volatility is not None and (
            not isfinite(self.max_annual_volatility) or self.max_annual_volatility <= 0
        ):
            raise ValueError("max_annual_volatility must be positive")


@dataclass(frozen=True)
class PortfolioRequest:
    returns: Mapping[str, Sequence[float]]
    constraints: PortfolioConstraints = field(default_factory=PortfolioConstraints)
    metadata: Mapping[str, AssetMetadata] = field(default_factory=dict)
    current_weights: Mapping[str, float] = field(default_factory=dict)
    return_dates: Sequence[date] = ()
    annualization_factor: int = 252

    def __post_init__(self) -> None:
        if len(self.returns) < 2:
            raise ValueError("at least two assets are required")
        lengths = {len(values) for values in self.returns.values()}
        if len(lengths) != 1 or next(iter(lengths)) < 2:
            raise ValueError("return series must have the same length and at least two values")
        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")
        if self.return_dates:
            observation_count = next(iter(lengths))
            if len(self.return_dates) != observation_count:
                raise ValueError("return_dates must match each return series")
            if any(
                current <= previous
                for previous, current in zip(self.return_dates, self.return_dates[1:])
            ):
                raise ValueError("return_dates must be strictly increasing")
        if any(
            not isfinite(float(value)) or not 0 <= float(value) <= 1
            for value in self.current_weights.values()
        ):
            raise ValueError("current_weights must be finite and between zero and one")
        if sum(float(value) for value in self.current_weights.values()) > 1 + 1e-8:
            raise ValueError("current_weights cannot exceed total portfolio capital")
        for symbol, values in self.returns.items():
            if not symbol.strip():
                raise ValueError("asset symbols cannot be empty")
            if any(not isfinite(float(value)) for value in values):
                raise ValueError("returns must be finite")
            if any(float(value) < -1 for value in values):
                raise ValueError("long-only asset returns cannot be below -100%")


@dataclass(frozen=True)
class AllocationResult:
    weights: Mapping[str, float]
    cash_weight: float
    backend: str
    expected_annual_return: float
    annual_volatility: float
    warnings: Sequence[str] = ()
    observations: int = 0
    historical_var_95: float = 0.0
    historical_expected_shortfall_95: float = 0.0
    historical_max_drawdown: float = 0.0
    effective_number_of_assets: float = 0.0
    turnover: float | None = None
    risk_contributions: Mapping[str, float] = field(default_factory=dict)
    group_exposures: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
