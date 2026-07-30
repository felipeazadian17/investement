from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from math import exp, isfinite, log1p
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from investement.valuation.fundamentals import LTMFundamentals

_FAMILY_FEATURES = {
    "growth": ("revenue_growth", "ebit_growth", "fcf_growth"),
    "profitability": (
        "gross_margin",
        "ebitda_margin",
        "ebit_margin",
        "net_margin",
        "roic",
        "roe",
        "cash_conversion",
    ),
    "capital_intensity": (
        "capex_to_revenue",
        "asset_turnover",
        "working_capital_to_revenue",
    ),
    "size": ("revenue", "enterprise_value", "market_cap", "total_assets"),
    "risk": (
        "net_debt_to_ebitda",
        "interest_coverage",
        "beta",
        "annual_volatility",
        "revenue_cyclicality",
        "sbc_to_revenue",
    ),
}

_DEFAULT_FAMILY_WEIGHTS = {
    "business": 0.30,
    "growth": 0.20,
    "profitability": 0.20,
    "capital_intensity": 0.10,
    "size": 0.10,
    "risk": 0.10,
}

_METRIC_FAMILY_WEIGHTS = {
    "PE": {
        "business": 0.25,
        "growth": 0.20,
        "profitability": 0.20,
        "capital_intensity": 0.05,
        "size": 0.10,
        "risk": 0.20,
    },
    "PB": {
        "business": 0.30,
        "growth": 0.15,
        "profitability": 0.25,
        "capital_intensity": 0.05,
        "size": 0.10,
        "risk": 0.15,
    },
    "PFCF": {
        "business": 0.30,
        "growth": 0.15,
        "profitability": 0.20,
        "capital_intensity": 0.20,
        "size": 0.10,
        "risk": 0.05,
    },
    "EVEBITDA": {
        "business": 0.30,
        "growth": 0.20,
        "profitability": 0.20,
        "capital_intensity": 0.15,
        "size": 0.10,
        "risk": 0.05,
    },
    "EVEBIT": {
        "business": 0.30,
        "growth": 0.15,
        "profitability": 0.20,
        "capital_intensity": 0.20,
        "size": 0.10,
        "risk": 0.05,
    },
    "EVSALES": {
        "business": 0.30,
        "growth": 0.25,
        "profitability": 0.25,
        "capital_intensity": 0.10,
        "size": 0.05,
        "risk": 0.05,
    },
}

_FINANCIAL_COMPANY_TYPES = frozenset({"bank", "insurance", "financial"})
_EARLY_LIFECYCLES = frozenset({"pre-revenue", "early-stage", "startup"})
_SIZE_FEATURES = frozenset(_FAMILY_FEATURES["size"])
SUPPORTED_PEER_METRICS = frozenset(
    name for feature_names in _FAMILY_FEATURES.values() for name in feature_names
)


class InsufficientComparablePeers(ValueError):
    def __init__(self, message: str, result=None) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class PeerProfile:
    symbol: str
    company_type: str
    sector: str
    industry: str | None = None
    sub_industry: str | None = None
    country: str | None = None
    accounting_standard: str | None = None
    lifecycle: str | None = None
    business_model: str | None = None
    revenue_mix: Mapping[str, float] = field(default_factory=dict)
    metrics: Mapping[str, float] = field(default_factory=dict)
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.company_type.strip() or not self.sector.strip():
            raise ValueError("peer profile requires symbol, company_type and sector")
        if self.as_of is not None and (
            self.as_of.tzinfo is None or self.as_of.utcoffset() is None
        ):
            raise ValueError("peer profile as_of must be timezone-aware")
        if any(not key.strip() for key in self.revenue_mix):
            raise ValueError("revenue mix labels cannot be blank")
        if any(not isfinite(value) or value < 0 for value in self.revenue_mix.values()):
            raise ValueError("revenue mix weights must be finite and non-negative")
        if self.revenue_mix and sum(self.revenue_mix.values()) <= 0:
            raise ValueError("revenue mix must have a positive total")
        if any(not key.strip() for key in self.metrics):
            raise ValueError("peer metric names cannot be blank")
        unknown_metrics = set(self.metrics) - SUPPORTED_PEER_METRICS
        if unknown_metrics:
            raise ValueError(f"unsupported peer metrics: {sorted(unknown_metrics)}")
        if any(not isfinite(value) for value in self.metrics.values()):
            raise ValueError("peer metrics must be finite")


@dataclass(frozen=True)
class ComparableObservation:
    symbol: str
    multiple: float
    metric: str
    profile: PeerProfile | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.metric.strip():
            raise ValueError("symbol and metric are required")
        if not isfinite(self.multiple) or self.multiple <= 0:
            raise ValueError("comparable multiple must be positive and finite")
        if self.profile is not None and self.profile.symbol.casefold() != self.symbol.casefold():
            raise ValueError("comparable observation and peer profile symbols must match")


@dataclass(frozen=True)
class PeerSelectionConfig:
    minimum_peers: int = 5
    maximum_peers: int = 12
    minimum_similarity: float = 0.55
    minimum_feature_coverage: float = 0.60
    family_weights: Mapping[str, float] = field(default_factory=dict)
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if self.minimum_peers < 2:
            raise ValueError("minimum_peers must be at least two")
        if self.maximum_peers < self.minimum_peers:
            raise ValueError("maximum_peers cannot be below minimum_peers")
        for value, name in (
            (self.minimum_similarity, "minimum_similarity"),
            (self.minimum_feature_coverage, "minimum_feature_coverage"),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between zero and one")
        unknown = set(self.family_weights) - set(_DEFAULT_FAMILY_WEIGHTS)
        if unknown:
            raise ValueError(f"unknown peer feature families: {sorted(unknown)}")
        if any(not isfinite(value) or value < 0 for value in self.family_weights.values()):
            raise ValueError("family weights must be finite and non-negative")
        if self.family_weights and sum(self.family_weights.values()) <= 0:
            raise ValueError("family weights must have a positive total")
        if self.as_of is not None and (
            self.as_of.tzinfo is None or self.as_of.utcoffset() is None
        ):
            raise ValueError("peer selection as_of must be timezone-aware")


@dataclass(frozen=True)
class PeerMatch:
    observation: ComparableObservation
    similarity_score: float
    feature_coverage: float
    family_scores: Mapping[str, float]
    reasons: Sequence[str]

    @property
    def symbol(self) -> str:
        return self.observation.symbol


@dataclass(frozen=True)
class PeerRejection:
    symbol: str
    reason: str


@dataclass(frozen=True)
class PeerSelectionResult:
    target_symbol: str
    metric: str
    selected: Sequence[PeerMatch]
    eligible_not_selected: Sequence[PeerMatch]
    rejected: Sequence[PeerRejection]

    @property
    def observations(self) -> tuple[ComparableObservation, ...]:
        return tuple(match.observation for match in self.selected)


@dataclass(frozen=True)
class RelativeValuationResult:
    metric: str
    target_metric_value: float
    selected_multiple: float
    value_per_share: float
    peer_count: int
    excluded_outliers: Sequence[str]
    selected_peers: Sequence[str] = ()
    implied_enterprise_value_per_share: float | None = None
    enterprise_to_equity_adjustment_per_share: float = 0.0


@dataclass(frozen=True)
class ComparableValuationTarget:
    metric: str
    target_metric_value: float
    enterprise_to_equity_adjustment_per_share: float = 0.0

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("comparable target metric is required")
        if not isfinite(self.target_metric_value) or self.target_metric_value <= 0:
            raise ValueError("comparable target metric value must be positive and finite")
        if not isfinite(self.enterprise_to_equity_adjustment_per_share):
            raise ValueError("enterprise-to-equity adjustment must be finite")


def peer_profile_from_fundamentals(
    fundamentals: "LTMFundamentals",
    latest_price: float,
    *,
    company_type: str,
    sector: str,
    industry: str | None = None,
    sub_industry: str | None = None,
    country: str | None = None,
    accounting_standard: str | None = None,
    lifecycle: str | None = None,
    business_model: str | None = None,
    revenue_mix: Mapping[str, float] | None = None,
    previous: "LTMFundamentals | None" = None,
    beta: float | None = None,
    annual_volatility: float | None = None,
    marginal_tax_rate: float | None = None,
    additional_metrics: Mapping[str, float] | None = None,
) -> PeerProfile:
    if not isfinite(latest_price) or latest_price <= 0:
        raise ValueError("latest_price must be positive and finite")
    shares = fundamentals.share_count
    if shares is None or shares <= 0:
        raise ValueError("peer profile requires a positive share count")
    market_cap = latest_price * shares
    enterprise_value = market_cap + fundamentals.equity_bridge.net_debt_equivalent
    metrics: dict[str, float] = {
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
    }
    _set_if_finite(metrics, "revenue", fundamentals.revenue)
    _set_if_finite(metrics, "total_assets", fundamentals.total_assets)

    revenue = fundamentals.revenue
    if revenue is not None and revenue > 0:
        _set_ratio(metrics, "ebit_margin", fundamentals.ebit, revenue)
        ebitda = _sum_if_complete(
            fundamentals.ebit,
            fundamentals.depreciation_and_amortization,
        )
        _set_ratio(metrics, "ebitda_margin", ebitda, revenue)
        _set_ratio(metrics, "net_margin", fundamentals.net_income, revenue)
        _set_ratio(metrics, "capex_to_revenue", fundamentals.capital_expenditure, revenue)
        _set_ratio(metrics, "asset_turnover", revenue, fundamentals.total_assets)
        _set_ratio(metrics, "sbc_to_revenue", fundamentals.stock_based_compensation, revenue)

    if fundamentals.net_income is not None and fundamentals.net_income > 0:
        _set_ratio(
            metrics,
            "cash_conversion",
            fundamentals.operating_cash_flow,
            fundamentals.net_income,
        )
    average_equity = _average_positive(
        fundamentals.total_equity,
        previous.total_equity if previous is not None else None,
    )
    _set_ratio(metrics, "roe", fundamentals.net_income, average_equity)

    tax_rate = marginal_tax_rate
    if tax_rate is None:
        effective = fundamentals.effective_tax_rate
        tax_rate = effective if effective is not None and 0 <= effective <= 0.60 else None
    invested_capital = _invested_capital(fundamentals)
    prior_invested_capital = _invested_capital(previous) if previous is not None else None
    average_invested_capital = _average_positive(invested_capital, prior_invested_capital)
    if tax_rate is not None and 0 <= tax_rate <= 1 and fundamentals.ebit is not None:
        _set_ratio(
            metrics,
            "roic",
            fundamentals.ebit * (1 - tax_rate),
            average_invested_capital,
        )

    _set_ratio(metrics, "interest_coverage", fundamentals.ebit, fundamentals.interest_expense)
    _set_ratio(
        metrics,
        "net_debt_to_ebitda",
        fundamentals.equity_bridge.net_debt_equivalent,
        _sum_if_complete(fundamentals.ebit, fundamentals.depreciation_and_amortization),
    )
    _set_if_finite(metrics, "beta", beta)
    _set_if_finite(metrics, "annual_volatility", annual_volatility)

    if previous is not None:
        _set_growth(metrics, "revenue_growth", fundamentals.revenue, previous.revenue)
        _set_growth(metrics, "ebit_growth", fundamentals.ebit, previous.ebit)
        _set_growth(
            metrics,
            "fcf_growth",
            fundamentals.levered_free_cash_flow,
            previous.levered_free_cash_flow,
        )
    for name, value in (additional_metrics or {}).items():
        if name not in SUPPORTED_PEER_METRICS:
            raise ValueError(f"unsupported peer metric: {name}")
        _set_if_finite(metrics, name, value)

    return PeerProfile(
        symbol=fundamentals.symbol,
        company_type=company_type,
        sector=sector,
        industry=industry or fundamentals.industry_code,
        sub_industry=sub_industry,
        country=country,
        accounting_standard=accounting_standard,
        lifecycle=lifecycle,
        business_model=business_model,
        revenue_mix=dict(revenue_mix or {}),
        metrics=metrics,
        as_of=fundamentals.available_at,
    )


def comparable_observation_from_fundamentals(
    profile: PeerProfile,
    fundamentals: "LTMFundamentals",
    metric: str,
) -> ComparableObservation:
    if profile.symbol.casefold() != fundamentals.symbol.casefold():
        raise ValueError("peer profile and fundamentals symbols must match")
    metric_key = _metric_key(metric)
    market_cap = profile.metrics.get("market_cap")
    enterprise_value = profile.metrics.get("enterprise_value")
    ebitda = _sum_if_complete(
        fundamentals.ebit,
        fundamentals.depreciation_and_amortization,
    )
    numerator_and_base = {
        "PE": (market_cap, fundamentals.net_income),
        "PB": (market_cap, fundamentals.total_equity),
        "PFCF": (market_cap, fundamentals.levered_free_cash_flow),
        "EVEBITDA": (enterprise_value, ebitda),
        "EVEBIT": (enterprise_value, fundamentals.ebit),
        "EVSALES": (enterprise_value, fundamentals.revenue),
    }
    if metric_key not in numerator_and_base:
        raise ValueError(f"unsupported comparable valuation metric: {metric}")
    numerator, base = numerator_and_base[metric_key]
    if numerator is None or base is None or numerator <= 0 or base <= 0:
        raise ValueError(f"{metric} requires positive numerator and denominator")
    return ComparableObservation(
        symbol=profile.symbol,
        multiple=numerator / base,
        metric=metric,
        profile=profile,
    )


def comparable_target_from_fundamentals(
    fundamentals: "LTMFundamentals",
    metric: str,
) -> ComparableValuationTarget:
    shares = fundamentals.share_count
    if shares is None or shares <= 0:
        raise ValueError("comparable target requires a positive share count")
    metric_key = _metric_key(metric)
    ebitda = _sum_if_complete(
        fundamentals.ebit,
        fundamentals.depreciation_and_amortization,
    )
    bases = {
        "PE": fundamentals.net_income,
        "PB": fundamentals.total_equity,
        "PFCF": fundamentals.levered_free_cash_flow,
        "EVEBITDA": ebitda,
        "EVEBIT": fundamentals.ebit,
        "EVSALES": fundamentals.revenue,
    }
    if metric_key not in bases:
        raise ValueError(f"unsupported comparable valuation metric: {metric}")
    base = bases[metric_key]
    if base is None or base <= 0:
        raise ValueError(f"{metric} requires a positive target denominator")
    adjustment = (
        fundamentals.equity_bridge.enterprise_to_equity_adjustment / shares
        if _is_enterprise_value_metric(metric)
        else 0.0
    )
    return ComparableValuationTarget(
        metric=metric,
        target_metric_value=base / shares,
        enterprise_to_equity_adjustment_per_share=adjustment,
    )


def select_comparable_peers(
    target: PeerProfile,
    observations: Iterable[ComparableObservation],
    metric: str,
    config: PeerSelectionConfig | None = None,
) -> PeerSelectionResult:
    active_config = config or PeerSelectionConfig()
    _validate_metric_for_company_type(metric, target.company_type)
    weights = _family_weights(metric, active_config.family_weights)
    candidates = [item for item in observations if _same_metric(item.metric, metric)]
    rejected: list[PeerRejection] = []
    gated_candidates: list[ComparableObservation] = []
    seen: set[str] = set()

    for observation in candidates:
        symbol_key = observation.symbol.casefold()
        if symbol_key in seen:
            rejected.append(PeerRejection(observation.symbol, "duplicate candidate"))
            continue
        seen.add(symbol_key)
        reason = _hard_gate_rejection(target, observation, active_config)
        if reason is not None:
            rejected.append(PeerRejection(observation.symbol, reason))
            continue
        gated_candidates.append(observation)

    profiles = [item.profile for item in gated_candidates if item.profile is not None]
    scales = _robust_feature_scales(target, profiles)
    matches: list[PeerMatch] = []
    for observation in gated_candidates:
        match = _score_peer(target, observation, weights, scales)
        if match.feature_coverage < active_config.minimum_feature_coverage:
            rejected.append(
                PeerRejection(
                    observation.symbol,
                    f"feature coverage {match.feature_coverage:.0%} is below "
                    f"{active_config.minimum_feature_coverage:.0%}",
                )
            )
        elif match.similarity_score < active_config.minimum_similarity:
            rejected.append(
                PeerRejection(
                    observation.symbol,
                    f"similarity {match.similarity_score:.0%} is below "
                    f"{active_config.minimum_similarity:.0%}",
                )
            )
        else:
            matches.append(match)

    matches.sort(key=lambda item: (-item.similarity_score, item.symbol.casefold()))
    selected = tuple(matches[: active_config.maximum_peers])
    result = PeerSelectionResult(
        target_symbol=target.symbol,
        metric=metric,
        selected=selected,
        eligible_not_selected=tuple(matches[active_config.maximum_peers :]),
        rejected=tuple(rejected),
    )
    if len(selected) < active_config.minimum_peers:
        raise InsufficientComparablePeers(
            f"{target.symbol} has {len(selected)} eligible peers for {metric}; "
            f"at least {active_config.minimum_peers} are required",
            result,
        )
    return result


def value_from_comparables(
    target_metric_value: float,
    observations: Iterable[ComparableObservation],
    metric: str,
    outlier_mad_limit: float | None = 3.5,
    enterprise_to_equity_adjustment_per_share: float | None = None,
) -> RelativeValuationResult:
    if not isfinite(target_metric_value) or target_metric_value <= 0:
        raise ValueError("target_metric_value must be positive and finite")
    selected = [item for item in observations if _same_metric(item.metric, metric)]
    if len(selected) < 2:
        raise ValueError("at least two comparable observations are required")
    if _is_enterprise_value_metric(metric) and enterprise_to_equity_adjustment_per_share is None:
        raise ValueError("enterprise-value multiples require an EV-to-equity bridge per share")
    adjustment = enterprise_to_equity_adjustment_per_share or 0.0
    if not isfinite(adjustment):
        raise ValueError("enterprise-to-equity adjustment must be finite")

    multiples = [item.multiple for item in selected]
    center = median(multiples)
    absolute_deviations = [abs(value - center) for value in multiples]
    mad = median(absolute_deviations)
    kept = selected
    excluded = []
    if outlier_mad_limit is not None and mad > 0:
        scale = 1.4826 * mad
        kept = [
            item for item in selected if abs(item.multiple - center) / scale <= outlier_mad_limit
        ]
        excluded = [item.symbol for item in selected if item not in kept]
    if len(kept) < 2:
        raise ValueError("outlier filtering left fewer than two peers")

    selected_multiple = median([item.multiple for item in kept])
    claim_value_per_share = target_metric_value * selected_multiple
    implied_enterprise_value = claim_value_per_share if _is_enterprise_value_metric(metric) else None
    return RelativeValuationResult(
        metric=metric,
        target_metric_value=target_metric_value,
        selected_multiple=selected_multiple,
        value_per_share=claim_value_per_share + adjustment,
        peer_count=len(kept),
        excluded_outliers=tuple(excluded),
        selected_peers=tuple(item.symbol for item in kept),
        implied_enterprise_value_per_share=implied_enterprise_value,
        enterprise_to_equity_adjustment_per_share=adjustment,
    )


def _validate_metric_for_company_type(metric: str, company_type: str) -> None:
    normalized_type = _normalize_label(company_type)
    if normalized_type in _FINANCIAL_COMPANY_TYPES and _metric_key(metric) in {
        "EVEBITDA",
        "EVEBIT",
        "EVFCF",
    }:
        raise ValueError(f"{metric} is not appropriate for {company_type} peer selection")


def _family_weights(metric: str, overrides: Mapping[str, float]) -> Mapping[str, float]:
    raw = dict(_METRIC_FAMILY_WEIGHTS.get(_metric_key(metric), _DEFAULT_FAMILY_WEIGHTS))
    raw.update(overrides)
    total = sum(raw.values())
    return {name: value / total for name, value in raw.items()}


def _hard_gate_rejection(
    target: PeerProfile,
    observation: ComparableObservation,
    config: PeerSelectionConfig,
) -> str | None:
    profile = observation.profile
    if profile is None:
        return "missing economic peer profile"
    if profile.symbol.casefold() == target.symbol.casefold():
        return "target company cannot be its own peer"
    if _normalize_label(profile.company_type) != _normalize_label(target.company_type):
        return "company type is not comparable"
    if _normalize_label(profile.sector) != _normalize_label(target.sector) and (
        not target.revenue_mix
        or not profile.revenue_mix
        or _mix_similarity(target.revenue_mix, profile.revenue_mix) < 0.50
    ):
        return "sector and business mix are not comparable"
    if _lifecycle_gate_fails(target.lifecycle, profile.lifecycle):
        return "life-cycle stage is not comparable"
    cutoff = config.as_of or target.as_of
    if cutoff is not None and profile.as_of is not None and profile.as_of > cutoff:
        return "peer profile was unavailable at the valuation cutoff"
    return None


def _lifecycle_gate_fails(target: str | None, candidate: str | None) -> bool:
    target_key = _normalize_label(target)
    candidate_key = _normalize_label(candidate)
    if not target_key or not candidate_key:
        return False
    if "distressed" in {target_key, candidate_key}:
        return target_key != candidate_key
    return (target_key in _EARLY_LIFECYCLES) != (candidate_key in _EARLY_LIFECYCLES)


def _score_peer(
    target: PeerProfile,
    observation: ComparableObservation,
    weights: Mapping[str, float],
    scales: Mapping[str, float],
) -> PeerMatch:
    candidate = observation.profile
    assert candidate is not None
    business_score, business_coverage = _business_similarity(target, candidate)
    family_scores = {"business": business_score}
    family_coverages = {"business": business_coverage}
    for family, features in _FAMILY_FEATURES.items():
        score, coverage = _numeric_family_similarity(target, candidate, features, scales)
        family_scores[family] = score
        family_coverages[family] = coverage

    similarity = sum(
        weights[family] * family_scores[family] * family_coverages[family]
        for family in weights
    )
    coverage = sum(weights[family] * family_coverages[family] for family in weights)
    return PeerMatch(
        observation=observation,
        similarity_score=max(0.0, min(similarity, 1.0)),
        feature_coverage=max(0.0, min(coverage, 1.0)),
        family_scores=family_scores,
        reasons=_match_reasons(target, candidate, family_scores),
    )


def _business_similarity(target: PeerProfile, candidate: PeerProfile) -> tuple[float, float]:
    comparisons = (
        ("sector", target.sector, candidate.sector, 0.15),
        ("industry", target.industry, candidate.industry, 0.25),
        ("sub-industry", target.sub_industry, candidate.sub_industry, 0.25),
        ("business model", target.business_model, candidate.business_model, 0.15),
        ("country", target.country, candidate.country, 0.05),
        (
            "accounting standard",
            target.accounting_standard,
            candidate.accounting_standard,
            0.05,
        ),
        ("life cycle", target.lifecycle, candidate.lifecycle, 0.05),
    )
    expected = sum(weight for _, target_value, _, weight in comparisons if target_value)
    available = sum(
        weight
        for _, target_value, candidate_value, weight in comparisons
        if target_value and candidate_value
    )
    matched = sum(
        weight
        for _, target_value, candidate_value, weight in comparisons
        if target_value
        and candidate_value
        and _normalize_label(target_value) == _normalize_label(candidate_value)
    )
    mix_weight = 0.10
    if target.revenue_mix:
        expected += mix_weight
        if candidate.revenue_mix:
            available += mix_weight
            matched += mix_weight * _mix_similarity(target.revenue_mix, candidate.revenue_mix)
    if expected <= 0:
        return 0.0, 0.0
    coverage = available / expected
    return (matched / available if available else 0.0), coverage


def _mix_similarity(target: Mapping[str, float], candidate: Mapping[str, float]) -> float:
    target_total = sum(target.values())
    candidate_total = sum(candidate.values())
    labels = set(target) | set(candidate)
    distance = sum(
        abs(target.get(label, 0.0) / target_total - candidate.get(label, 0.0) / candidate_total)
        for label in labels
    ) / 2
    return max(0.0, 1 - distance)


def _numeric_family_similarity(
    target: PeerProfile,
    candidate: PeerProfile,
    features: Sequence[str],
    scales: Mapping[str, float],
) -> tuple[float, float]:
    expected = [name for name in features if name in target.metrics]
    if not expected:
        return 0.0, 0.0
    shared = [name for name in expected if name in candidate.metrics]
    if not shared:
        return 0.0, 0.0
    similarities = []
    for name in shared:
        target_value = _transform_metric(name, target.metrics[name])
        candidate_value = _transform_metric(name, candidate.metrics[name])
        robust_distance = min(abs(target_value - candidate_value) / scales[name], 8.0)
        similarities.append(exp(-robust_distance))
    return sum(similarities) / len(similarities), len(shared) / len(expected)


def _robust_feature_scales(
    target: PeerProfile,
    profiles: Sequence[PeerProfile],
) -> Mapping[str, float]:
    scales = {}
    for feature in {name for names in _FAMILY_FEATURES.values() for name in names}:
        values = [
            _transform_metric(feature, profile.metrics[feature])
            for profile in (target, *profiles)
            if feature in profile.metrics
        ]
        if not values:
            continue
        center = median(values)
        mad = median(abs(value - center) for value in values)
        fallback = max(max(values) - min(values), abs(center) * 0.10, 1e-9)
        scales[feature] = 1.4826 * mad if mad > 0 else fallback
    return scales


def _transform_metric(name: str, value: float) -> float:
    if name not in _SIZE_FEATURES:
        return value
    return log1p(value) if value >= 0 else -log1p(abs(value))


def _match_reasons(
    target: PeerProfile,
    candidate: PeerProfile,
    family_scores: Mapping[str, float],
) -> tuple[str, ...]:
    reasons = []
    if target.sub_industry and _normalize_label(target.sub_industry) == _normalize_label(
        candidate.sub_industry
    ):
        reasons.append(f"same sub-industry: {target.sub_industry}")
    elif target.industry and _normalize_label(target.industry) == _normalize_label(
        candidate.industry
    ):
        reasons.append(f"same industry: {target.industry}")
    elif _normalize_label(target.sector) == _normalize_label(candidate.sector):
        reasons.append(f"same sector: {target.sector}")
    ranked = sorted(
        (
            (name, score)
            for name, score in family_scores.items()
            if name != "business" and score > 0
        ),
        key=lambda item: (-item[1], item[0]),
    )
    reasons.extend(f"{name.replace('_', ' ')} similarity {score:.0%}" for name, score in ranked[:2])
    return tuple(reasons)


def _same_metric(left: str, right: str) -> bool:
    return _metric_key(left) == _metric_key(right)


def _is_enterprise_value_metric(metric: str) -> bool:
    return _metric_key(metric).startswith("EV")


def _metric_key(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _normalize_label(value: str | None) -> str:
    if value is None:
        return ""
    return "-".join(value.strip().casefold().replace("_", "-").split())


def _set_if_finite(metrics: dict[str, float], name: str, value: float | None) -> None:
    if value is not None and isfinite(value):
        metrics[name] = float(value)


def _set_ratio(
    metrics: dict[str, float],
    name: str,
    numerator: float | None,
    denominator: float | None,
) -> None:
    if (
        numerator is not None
        and denominator is not None
        and isfinite(numerator)
        and isfinite(denominator)
        and denominator != 0
    ):
        metrics[name] = numerator / denominator


def _set_growth(
    metrics: dict[str, float],
    name: str,
    current: float | None,
    previous: float | None,
) -> None:
    if (
        current is not None
        and previous is not None
        and isfinite(current)
        and isfinite(previous)
        and previous != 0
    ):
        metrics[name] = (current - previous) / abs(previous)


def _sum_if_complete(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left + right


def _average_positive(current: float | None, previous: float | None) -> float | None:
    values = [value for value in (current, previous) if value is not None and value > 0]
    return sum(values) / len(values) if values else None


def _invested_capital(fundamentals: "LTMFundamentals | None") -> float | None:
    if fundamentals is None or fundamentals.total_equity is None:
        return None
    return (
        fundamentals.total_equity
        + (fundamentals.total_debt or 0.0)
        + (fundamentals.operating_lease_liabilities or 0.0)
        - (fundamentals.cash_and_equivalents or 0.0)
        - (fundamentals.short_term_investments or 0.0)
        - (fundamentals.long_term_investments or 0.0)
    )
