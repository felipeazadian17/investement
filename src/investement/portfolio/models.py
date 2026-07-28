from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True)
class AssetMetadata:
    sector: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class PortfolioConstraints:
    min_weight: float = 0.0
    max_weight: float = 0.25
    min_cash: float = 0.0
    asset_max_weights: Mapping[str, float] = field(default_factory=dict)
    sector_max_weights: Mapping[str, float] = field(default_factory=dict)
    country_max_weights: Mapping[str, float] = field(default_factory=dict)

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
        ):
            if any(not isfinite(value) or not 0 <= value <= 1 for value in limits.values()):
                raise ValueError("all constraint limits must be between 0 and 1")


@dataclass(frozen=True)
class PortfolioRequest:
    returns: Mapping[str, Sequence[float]]
    constraints: PortfolioConstraints = field(default_factory=PortfolioConstraints)
    metadata: Mapping[str, AssetMetadata] = field(default_factory=dict)
    current_weights: Mapping[str, float] = field(default_factory=dict)
    annualization_factor: int = 252

    def __post_init__(self) -> None:
        if len(self.returns) < 2:
            raise ValueError("at least two assets are required")
        lengths = {len(values) for values in self.returns.values()}
        if len(lengths) != 1 or next(iter(lengths)) < 2:
            raise ValueError("return series must have the same length and at least two values")
        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")
        for symbol, values in self.returns.items():
            if not symbol.strip():
                raise ValueError("asset symbols cannot be empty")
            if any(not isfinite(float(value)) for value in values):
                raise ValueError("returns must be finite")


@dataclass(frozen=True)
class AllocationResult:
    weights: Mapping[str, float]
    cash_weight: float
    backend: str
    expected_annual_return: float
    annual_volatility: float
    warnings: Sequence[str] = ()
