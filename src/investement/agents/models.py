from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Any

from investement.domain import PriceBar, SignalAction, require_aware
from investement.orchestration import AgentFinding, CommitteeDecision, EvidenceReference
from investement.portfolio import AllocationResult, AssetMetadata, PortfolioConstraints
from investement.valuation import (
    ComparableObservation,
    DCFResult,
    RelativeValuationResult,
    ValuationSignal,
)


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True)
class InvestorProfileRequest:
    objectives: Sequence[str]
    horizon_years: int
    base_currency: str
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    min_cash_weight: float = 0.05
    max_position_weight: float = 0.25
    max_drawdown: float = 0.25
    max_annual_volatility: float | None = None
    minimum_daily_dollar_volume: float = 0.0
    prohibited_symbols: Sequence[str] = ()
    prohibited_sectors: Sequence[str] = ()
    prohibited_countries: Sequence[str] = ()
    sector_max_weights: Mapping[str, float] = field(default_factory=dict)
    country_max_weights: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.objectives or any(not item.strip() for item in self.objectives):
            raise ValueError("at least one non-empty investment objective is required")
        if self.horizon_years <= 0:
            raise ValueError("horizon_years must be positive")
        if len(self.base_currency.strip()) != 3 or not self.base_currency.isalpha():
            raise ValueError("base_currency must be a three-letter currency code")
        for value, name in (
            (self.min_cash_weight, "min_cash_weight"),
            (self.max_position_weight, "max_position_weight"),
            (self.max_drawdown, "max_drawdown"),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.max_position_weight <= 0 or self.max_drawdown <= 0:
            raise ValueError("position and drawdown limits must be positive")
        if self.max_annual_volatility is not None and (
            not isfinite(self.max_annual_volatility) or self.max_annual_volatility <= 0
        ):
            raise ValueError("max_annual_volatility must be positive")
        if not isfinite(self.minimum_daily_dollar_volume) or self.minimum_daily_dollar_volume < 0:
            raise ValueError("minimum_daily_dollar_volume cannot be negative")
        for limits in (self.sector_max_weights, self.country_max_weights):
            if any(not isfinite(value) or not 0 <= value <= 1 for value in limits.values()):
                raise ValueError("group weight limits must be between 0 and 1")


@dataclass(frozen=True)
class InvestorProfile:
    objectives: Sequence[str]
    horizon_years: int
    base_currency: str
    risk_tolerance: RiskTolerance
    min_cash_weight: float
    max_position_weight: float
    max_drawdown: float
    max_annual_volatility: float
    minimum_daily_dollar_volume: float
    prohibited_symbols: frozenset[str]
    prohibited_sectors: frozenset[str]
    prohibited_countries: frozenset[str]
    sector_max_weights: Mapping[str, float]
    country_max_weights: Mapping[str, float]

    def portfolio_constraints(
        self,
        asset_max_weights: Mapping[str, float] | None = None,
    ) -> PortfolioConstraints:
        return PortfolioConstraints(
            max_weight=self.max_position_weight,
            min_cash=self.min_cash_weight,
            asset_max_weights=dict(asset_max_weights or {}),
            sector_max_weights=dict(self.sector_max_weights),
            country_max_weights=dict(self.country_max_weights),
        )


@dataclass(frozen=True)
class AssetDataRequest:
    symbol: str
    start: date
    end: date
    as_of: datetime
    interval: str = "1d"
    filing_forms: Sequence[str] = ("10-K", "10-Q")
    filing_limit: int = 4

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.interval.strip():
            raise ValueError("symbol and interval are required")
        if self.start > self.end:
            raise ValueError("start cannot be after end")
        require_aware(self.as_of, "as_of")
        if self.start > self.as_of.date():
            raise ValueError("start cannot be after as_of")
        if self.filing_limit < 0:
            raise ValueError("filing_limit cannot be negative")


@dataclass(frozen=True)
class AssetDataSnapshot:
    symbol: str
    as_of: datetime
    retrieved_at: datetime
    bars: Sequence[PriceBar]
    filings: Sequence[Any]
    evidence: Sequence[EvidenceReference]

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.bars or not self.evidence:
            raise ValueError("snapshot requires a symbol, price bars and evidence")
        require_aware(self.as_of, "as_of")
        require_aware(self.retrieved_at, "retrieved_at")
        if any(bar.timestamp > self.as_of for bar in self.bars):
            raise ValueError("snapshot contains a price bar after as_of")
        if any(bar.provenance.available_at > self.as_of for bar in self.bars):
            raise ValueError("snapshot contains data that was unavailable at as_of")

    @property
    def latest_price(self) -> float:
        return float(self.bars[-1].adjusted_close)


@dataclass(frozen=True)
class FundamentalModelInputs:
    base_free_cash_flow: float
    growth_rates: Sequence[float]
    discount_rate: float
    terminal_growth_rate: float
    net_debt: float
    diluted_shares: float
    roic: float | None = None
    revenue_growth: float | None = None
    operating_margin: float | None = None
    debt_to_free_cash_flow: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.base_free_cash_flow,
            self.discount_rate,
            self.terminal_growth_rate,
            self.net_debt,
            self.diluted_shares,
            *self.growth_rates,
        )
        if not self.growth_rates or any(not isfinite(float(value)) for value in values):
            raise ValueError("fundamental model inputs must be finite")
        for optional in (
            self.roic,
            self.revenue_growth,
            self.operating_margin,
            self.debt_to_free_cash_flow,
        ):
            if optional is not None and not isfinite(optional):
                raise ValueError("optional quality metrics must be finite")


@dataclass(frozen=True)
class FundamentalAnalysis:
    dcf: DCFResult
    projected_free_cash_flows: Sequence[float]
    quality_score: float
    finding: AgentFinding


@dataclass(frozen=True)
class TechnicalAnalysis:
    short_moving_average: float
    long_moving_average: float
    momentum: float
    rsi: float
    macd: float
    macd_signal: float
    annual_volatility: float
    max_drawdown: float
    finding: AgentFinding


@dataclass(frozen=True)
class RelativeValuationInputs:
    target_metric_value: float
    metric: str
    comparables: Sequence[ComparableObservation]
    dcf_weight: float = 0.60
    required_margin: float = 0.20
    sell_premium: float = 0.20

    def __post_init__(self) -> None:
        if not isfinite(self.target_metric_value) or self.target_metric_value <= 0:
            raise ValueError("target_metric_value must be positive")
        if not self.metric.strip() or not self.comparables:
            raise ValueError("metric and comparable observations are required")
        for value, name in (
            (self.dcf_weight, "dcf_weight"),
            (self.required_margin, "required_margin"),
            (self.sell_premium, "sell_premium"),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class RelativeValuationAnalysis:
    comparables: RelativeValuationResult
    blended_fair_value: float
    signal: ValuationSignal
    finding: AgentFinding


@dataclass(frozen=True)
class RebalanceInstruction:
    symbol: str
    current_weight: float
    target_weight: float
    change: float
    action: SignalAction


@dataclass(frozen=True)
class PortfolioPlan:
    allocation: AllocationResult
    rebalances: Sequence[RebalanceInstruction]
    eligible_assets: Sequence[str]
    excluded_assets: Mapping[str, str]


@dataclass(frozen=True)
class RiskAssessment:
    subject: str
    approved: bool
    breaches: Sequence[str]
    metrics: Mapping[str, float]
    finding: AgentFinding


@dataclass(frozen=True)
class PortfolioRecommendation:
    plan: PortfolioPlan
    risk: RiskAssessment
    approved: bool


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    retrieved_at: datetime
    account_numbers: Sequence[Mapping[str, Any]]
    accounts: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class AuditReceipt:
    event_hash: str
    memory_key: str | None
    chain_valid: bool


@dataclass(frozen=True)
class AssetAnalysisRequest:
    profile: InvestorProfile
    data: AssetDataRequest
    fundamentals: FundamentalModelInputs
    relative_valuation: RelativeValuationInputs
    proposed_weight: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.proposed_weight) or not 0 <= self.proposed_weight <= 1:
            raise ValueError("proposed_weight must be between 0 and 1")


@dataclass(frozen=True)
class AssetAnalysisReport:
    run_id: str
    symbol: str
    snapshot: AssetDataSnapshot
    fundamental: FundamentalAnalysis
    technical: TechnicalAnalysis
    relative_valuation: RelativeValuationAnalysis
    risk: RiskAssessment
    decision: CommitteeDecision
    audit_receipt: AuditReceipt | None = None


@dataclass(frozen=True)
class PortfolioConstructionInputs:
    profile: InvestorProfile
    returns: Mapping[str, Sequence[float]]
    metadata: Mapping[str, AssetMetadata] = field(default_factory=dict)
    current_weights: Mapping[str, float] = field(default_factory=dict)
    decisions: Mapping[str, CommitteeDecision] = field(default_factory=dict)
    backend: str = "inverse_volatility"
