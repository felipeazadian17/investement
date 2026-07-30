from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Any

from investement.domain import (
    CorporateAction,
    FundamentalSnapshot,
    FundSnapshot,
    MarketDataReconciliation,
    OptionChainSnapshot,
    PriceBar,
    SignalAction,
    require_aware,
)
from investement.orchestration import AgentFinding, CommitteeDecision, EvidenceReference
from investement.portfolio import AllocationResult, AssetMetadata, PortfolioConstraints
from investement.valuation import (
    CapitalCostResult,
    ComparableObservation,
    DCFResult,
    LTMFundamentals,
    OperatingProjection,
    PeerProfile,
    PeerSelectionConfig,
    PeerSelectionResult,
    RelativeValuationResult,
    ValuationSignal,
)


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class IncomeStability(str, Enum):
    UNSTABLE = "unstable"
    VARIABLE = "variable"
    STABLE = "stable"


class InvestmentExperience(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class TechnicalRegime(str, Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class TechnicalTimingAction(str, Enum):
    FAVOR_ENTRY = "favor_entry"
    HOLD = "hold"
    WAIT = "wait"
    TIGHTEN_RISK = "tighten_risk"
    FAVOR_EXIT = "favor_exit"


class LeveragePolicy(str, Enum):
    PROHIBITED = "prohibited"
    EXCEPTIONAL = "exceptional"
    ALLOWED = "allowed"


@dataclass(frozen=True)
class TaxPolicy:
    jurisdiction: str
    rules_as_of: date
    foreign_investment_income_taxable: bool | None = None
    foreign_capital_gains_taxable: bool | None = None
    foreign_tax_credit_available: bool | None = None
    tax_lot_method: str | None = None
    us_situs_estate_tax_threshold: float | None = None
    prefer_non_us_domiciled_funds: bool = False
    professional_review_required: bool = True
    source_urls: Sequence[str] = ()

    def __post_init__(self) -> None:
        if len(self.jurisdiction.strip()) != 2 or not self.jurisdiction.isalpha():
            raise ValueError("tax jurisdiction must be a two-letter country code")
        if self.us_situs_estate_tax_threshold is not None and (
            not isfinite(self.us_situs_estate_tax_threshold)
            or self.us_situs_estate_tax_threshold < 0
        ):
            raise ValueError("US-situs estate tax threshold cannot be negative")
        if self.tax_lot_method is not None and not self.tax_lot_method.strip():
            raise ValueError("tax_lot_method cannot be blank")
        if any(not item.strip() for item in self.source_urls):
            raise ValueError("tax source URLs cannot be blank")


@dataclass(frozen=True)
class RiskProfileAssessment:
    capacity: RiskTolerance
    willingness: RiskTolerance
    need: RiskTolerance
    effective: RiskTolerance
    capacity_score: int
    reasons: Sequence[str]


@dataclass(frozen=True)
class InvestorProfileRequest:
    objectives: Sequence[str]
    horizon_years: int
    base_currency: str
    risk_tolerance: RiskTolerance | None = None
    min_cash_weight: float = 0.05
    max_position_weight: float = 0.25
    max_drawdown: float = 0.25
    max_annual_volatility: float | None = None
    max_portfolio_annual_volatility: float | None = None
    max_asset_drawdown: float | None = None
    minimum_daily_dollar_volume: float = 0.0
    prohibited_symbols: Sequence[str] = ()
    prohibited_sectors: Sequence[str] = ()
    prohibited_countries: Sequence[str] = ()
    sector_max_weights: Mapping[str, float] = field(default_factory=dict)
    country_max_weights: Mapping[str, float] = field(default_factory=dict)
    asset_class_max_weights: Mapping[str, float] = field(default_factory=dict)
    currency_max_weights: Mapping[str, float] = field(default_factory=dict)
    age: int | None = None
    residence_country: str | None = None
    tax_residency: str | None = None
    monthly_net_income: float | None = None
    monthly_expenses: float | None = None
    liquid_net_worth: float | None = None
    portfolio_funding: float | None = None
    external_emergency_reserve: float = 0.0
    emergency_fund_months_target: float = 6.0
    dependents: int = 0
    income_stability: IncomeStability = IncomeStability.VARIABLE
    investment_experience: InvestmentExperience = InvestmentExperience.INTERMEDIATE
    short_selling_allowed: bool = False
    leverage_policy: LeveragePolicy = LeveragePolicy.PROHIBITED
    preferred_styles: Sequence[str] = ()
    prefers_dividends: bool = False
    requires_fixed_income: bool = False
    tax_policy: TaxPolicy | None = None
    profile_as_of: date | None = None

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
        if self.max_portfolio_annual_volatility is not None and (
            not isfinite(self.max_portfolio_annual_volatility)
            or self.max_portfolio_annual_volatility <= 0
        ):
            raise ValueError("max_portfolio_annual_volatility must be positive")
        if self.max_asset_drawdown is not None and (
            not isfinite(self.max_asset_drawdown) or not 0 < self.max_asset_drawdown <= 1
        ):
            raise ValueError("max_asset_drawdown must be between zero and one")
        if not isfinite(self.minimum_daily_dollar_volume) or self.minimum_daily_dollar_volume < 0:
            raise ValueError("minimum_daily_dollar_volume cannot be negative")
        for limits in (
            self.sector_max_weights,
            self.country_max_weights,
            self.asset_class_max_weights,
            self.currency_max_weights,
        ):
            if any(not isfinite(value) or not 0 <= value <= 1 for value in limits.values()):
                raise ValueError("group weight limits must be between 0 and 1")
        if self.age is not None and not 18 <= self.age <= 120:
            raise ValueError("age must be between 18 and 120")
        for country, name in (
            (self.residence_country, "residence_country"),
            (self.tax_residency, "tax_residency"),
        ):
            if country is not None and (len(country.strip()) != 2 or not country.isalpha()):
                raise ValueError(f"{name} must be a two-letter country code")
        for value, name in (
            (self.monthly_net_income, "monthly_net_income"),
            (self.monthly_expenses, "monthly_expenses"),
            (self.liquid_net_worth, "liquid_net_worth"),
            (self.portfolio_funding, "portfolio_funding"),
        ):
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{name} cannot be negative")
        for value, name in (
            (self.external_emergency_reserve, "external_emergency_reserve"),
            (self.emergency_fund_months_target, "emergency_fund_months_target"),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.dependents < 0:
            raise ValueError("dependents cannot be negative")
        if any(not item.strip() for item in self.preferred_styles):
            raise ValueError("preferred investment styles cannot be blank")


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
    max_portfolio_annual_volatility: float
    max_asset_drawdown: float
    minimum_daily_dollar_volume: float
    prohibited_symbols: frozenset[str]
    prohibited_sectors: frozenset[str]
    prohibited_countries: frozenset[str]
    sector_max_weights: Mapping[str, float]
    country_max_weights: Mapping[str, float]
    asset_class_max_weights: Mapping[str, float]
    currency_max_weights: Mapping[str, float]
    age: int | None
    residence_country: str | None
    tax_residency: str | None
    monthly_surplus: float | None
    emergency_reserve_target: float | None
    unfunded_emergency_reserve: float
    investable_assets_after_reserve: float | None
    dependents: int
    income_stability: IncomeStability
    investment_experience: InvestmentExperience
    short_selling_allowed: bool
    leverage_policy: LeveragePolicy
    preferred_styles: Sequence[str]
    prefers_dividends: bool
    requires_fixed_income: bool
    risk_assessment: RiskProfileAssessment
    tax_policy: TaxPolicy | None
    profile_as_of: date | None

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
            asset_class_max_weights=dict(self.asset_class_max_weights),
            currency_max_weights=dict(self.currency_max_weights),
            max_annual_volatility=self.max_portfolio_annual_volatility,
        )


@dataclass(frozen=True)
class AssetDataRequest:
    symbol: str
    start: date
    end: date
    as_of: datetime
    interval: str = "1d"
    filing_forms: Sequence[str] = ("10-K", "10-Q")
    filing_limit: int = 8
    include_fundamentals: bool = True
    include_fund_data: bool = False
    option_expiration: date | None = None

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
    fundamentals: Sequence[FundamentalSnapshot] = ()
    corporate_actions: Sequence[CorporateAction] = ()
    fund: FundSnapshot | None = None
    option_chain: OptionChainSnapshot | None = None
    reconciliation: MarketDataReconciliation | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.bars or not self.evidence:
            raise ValueError("snapshot requires a symbol, price bars and evidence")
        require_aware(self.as_of, "as_of")
        require_aware(self.retrieved_at, "retrieved_at")
        if any(bar.timestamp > self.as_of for bar in self.bars):
            raise ValueError("snapshot contains a price bar after as_of")
        if any(bar.provenance.available_at > self.as_of for bar in self.bars):
            raise ValueError("snapshot contains data that was unavailable at as_of")
        if any(item.provenance.available_at > self.as_of for item in self.fundamentals):
            raise ValueError("snapshot contains fundamentals that were unavailable at as_of")
        if any(item.provenance.available_at > self.as_of for item in self.corporate_actions):
            raise ValueError("snapshot contains corporate actions that were unavailable at as_of")
        if self.fund is not None and self.fund.provenance.available_at > self.as_of:
            raise ValueError("snapshot contains fund data that was unavailable at as_of")
        if self.option_chain is not None and self.option_chain.provenance.available_at > self.as_of:
            raise ValueError("snapshot contains option data that was unavailable at as_of")

    @property
    def latest_price(self) -> float:
        return float(self.bars[-1].close)


@dataclass(frozen=True)
class FundamentalAnalysis:
    dcf: DCFResult
    projected_free_cash_flows: Sequence[float]
    quality_score: float
    finding: AgentFinding
    ltm: LTMFundamentals | None = None
    capital_cost: CapitalCostResult | None = None
    projection: OperatingProjection | None = None
    sensitivity: Mapping[float, Mapping[float, float | None]] = field(default_factory=dict)
    model_assumptions: Mapping[str, float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class TechnicalTimingSignal:
    action: TechnicalTimingAction
    strength: float
    confidence: float
    observed_at: datetime
    valid_for_bars: int
    execute_on_next_bar: bool
    reasons: Sequence[str]
    invalidation_conditions: Sequence[str]

    def __post_init__(self) -> None:
        if not isfinite(self.strength) or not -1 <= self.strength <= 1:
            raise ValueError("technical timing strength must be between -1 and 1")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("technical timing confidence must be between zero and one")
        require_aware(self.observed_at, "technical timing observed_at")
        if self.valid_for_bars <= 0:
            raise ValueError("technical timing validity must be positive")
        if not self.execute_on_next_bar:
            raise ValueError("technical timing cannot execute on the observation bar")
        if not self.reasons or any(not item.strip() for item in self.reasons):
            raise ValueError("technical timing requires non-empty reasons")
        if not self.invalidation_conditions or any(
            not item.strip() for item in self.invalidation_conditions
        ):
            raise ValueError("technical timing requires non-empty invalidation conditions")


@dataclass(frozen=True)
class TechnicalAnalysis:
    short_moving_average: float
    long_moving_average: float
    momentum: float
    medium_momentum: float
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    normalized_atr: float
    volume_ratio: float | None
    annual_volatility: float
    max_drawdown: float
    current_drawdown: float
    trend_regime: TechnicalRegime
    timing: TechnicalTimingSignal
    parameters: Mapping[str, float | int]
    finding: AgentFinding


@dataclass(frozen=True)
class RelativeValuationInputs:
    target_metric_value: float
    metric: str
    comparables: Sequence[ComparableObservation]
    target_peer_profile: PeerProfile | None = None
    peer_selection_config: PeerSelectionConfig = field(default_factory=PeerSelectionConfig)
    enterprise_to_equity_adjustment_per_share: float | None = None
    dcf_weight: float = 0.60
    required_margin: float = 0.20
    sell_premium: float = 0.20

    def __post_init__(self) -> None:
        if not isfinite(self.target_metric_value) or self.target_metric_value <= 0:
            raise ValueError("target_metric_value must be positive")
        if not self.metric.strip() or not self.comparables:
            raise ValueError("metric and comparable observations are required")
        if self.target_peer_profile is not None and any(
            item.profile is None for item in self.comparables
        ):
            raise ValueError("automatic peer selection requires a profile for every candidate")
        if self.enterprise_to_equity_adjustment_per_share is not None and not isfinite(
            self.enterprise_to_equity_adjustment_per_share
        ):
            raise ValueError("enterprise-to-equity adjustment must be finite")
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
    peer_selection: PeerSelectionResult | None = None
    comparable_signal: ValuationSignal | None = None


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
    implementation_turnover: float = 0.0


@dataclass(frozen=True)
class RiskAssessment:
    subject: str
    approved: bool
    breaches: Sequence[str]
    metrics: Mapping[str, float]
    finding: AgentFinding
    warnings: Sequence[str] = ()


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
class BrokerPortfolioState:
    retrieved_at: datetime
    provider: str
    base_currency: str
    total_value: float
    cash_value: float
    cash_weight: float
    position_values: Mapping[str, float]
    current_weights: Mapping[str, float]

    def __post_init__(self) -> None:
        require_aware(self.retrieved_at, "retrieved_at")
        if not self.provider.strip():
            raise ValueError("broker provider is required")
        if len(self.base_currency.strip()) != 3 or not self.base_currency.isalpha():
            raise ValueError("base_currency must be a three-letter currency code")
        if not isfinite(self.total_value) or self.total_value <= 0:
            raise ValueError("broker total value must be positive")
        if not isfinite(self.cash_value) or self.cash_value < 0:
            raise ValueError("broker cash value cannot be negative")
        if not isfinite(self.cash_weight) or not 0 <= self.cash_weight <= 1:
            raise ValueError("broker cash weight must be between zero and one")
        if any(not isfinite(value) or value < 0 for value in self.position_values.values()):
            raise ValueError("broker position values cannot be negative")
        if any(not isfinite(value) or not 0 <= value <= 1 for value in self.current_weights.values()):
            raise ValueError("broker current weights must be between zero and one")
        if sum(self.current_weights.values()) + self.cash_weight > 1 + 1e-6:
            raise ValueError("broker positions and cash cannot exceed total value")


@dataclass(frozen=True)
class BrokerAwarePortfolioRecommendation:
    current: BrokerPortfolioState
    current_risk: RiskAssessment
    target: PortfolioRecommendation


@dataclass(frozen=True)
class AuditReceipt:
    event_hash: str
    memory_key: str | None
    chain_valid: bool


@dataclass(frozen=True)
class AssetAnalysisRequest:
    profile: InvestorProfile
    data: AssetDataRequest
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
    return_dates: Sequence[date] = ()
    backend: str = "inverse_volatility"
    absolute_rebalance_band: float = 0.01
    relative_rebalance_band: float = 0.20

    def __post_init__(self) -> None:
        for value, name in (
            (self.absolute_rebalance_band, "absolute_rebalance_band"),
            (self.relative_rebalance_band, "relative_rebalance_band"),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between zero and one")
