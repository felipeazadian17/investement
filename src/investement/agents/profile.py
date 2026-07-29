import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from investement.agents.models import (
    IncomeStability,
    InvestmentExperience,
    InvestorProfile,
    InvestorProfileRequest,
    LeveragePolicy,
    RiskProfileAssessment,
    RiskTolerance,
    TaxPolicy,
)

_DEFAULT_ASSET_VOLATILITY_LIMITS = {
    RiskTolerance.CONSERVATIVE: 0.20,
    RiskTolerance.MODERATE: 0.35,
    RiskTolerance.AGGRESSIVE: 0.55,
}
_PERSONAL_POSITION_LIMITS = {
    RiskTolerance.CONSERVATIVE: 0.04,
    RiskTolerance.MODERATE: 0.06,
    RiskTolerance.AGGRESSIVE: 0.10,
}
_RISK_ORDER = {
    RiskTolerance.CONSERVATIVE: 0,
    RiskTolerance.MODERATE: 1,
    RiskTolerance.AGGRESSIVE: 2,
}


class InvestorProfileAgent:
    name = "investor-profile"

    def create(self, request: InvestorProfileRequest) -> InvestorProfile:
        assessment = _assess_risk(request)
        has_financial_context = _has_financial_context(request)
        emergency_reserve_target = _emergency_reserve_target(request)
        unfunded_reserve = max(
            (emergency_reserve_target or 0.0) - request.external_emergency_reserve,
            0.0,
        )
        min_cash_weight = request.min_cash_weight
        if request.portfolio_funding and unfunded_reserve:
            min_cash_weight = max(
                min_cash_weight,
                min(unfunded_reserve / request.portfolio_funding, 1.0),
            )
        max_position_weight = request.max_position_weight
        if has_financial_context:
            max_position_weight = min(
                max_position_weight,
                _PERSONAL_POSITION_LIMITS[assessment.effective],
            )
        max_asset_volatility = request.max_annual_volatility
        if max_asset_volatility is None:
            max_asset_volatility = _DEFAULT_ASSET_VOLATILITY_LIMITS[assessment.effective]
        max_portfolio_volatility = request.max_portfolio_annual_volatility
        if max_portfolio_volatility is None:
            max_portfolio_volatility = (
                min(max_asset_volatility, max(0.08, request.max_drawdown * 0.90))
                if has_financial_context
                else max_asset_volatility
            )
        max_asset_drawdown = request.max_asset_drawdown
        if max_asset_drawdown is None:
            max_asset_drawdown = (
                max(request.max_drawdown, 0.45) if has_financial_context else request.max_drawdown
            )
        if (
            request.tax_policy is not None
            and request.tax_residency is not None
            and request.tax_policy.jurisdiction.casefold() != request.tax_residency.casefold()
        ):
            raise ValueError("tax policy jurisdiction must match tax residency")
        monthly_surplus = _monthly_surplus(request)
        investable_after_reserve = (
            max(request.portfolio_funding - unfunded_reserve, 0.0)
            if request.portfolio_funding is not None
            else None
        )
        return InvestorProfile(
            objectives=tuple(item.strip() for item in request.objectives),
            horizon_years=request.horizon_years,
            base_currency=request.base_currency.strip().upper(),
            risk_tolerance=assessment.effective,
            min_cash_weight=min_cash_weight,
            max_position_weight=max_position_weight,
            max_drawdown=request.max_drawdown,
            max_annual_volatility=max_asset_volatility,
            max_portfolio_annual_volatility=max_portfolio_volatility,
            max_asset_drawdown=max_asset_drawdown,
            minimum_daily_dollar_volume=request.minimum_daily_dollar_volume,
            prohibited_symbols=frozenset(
                item.strip().upper() for item in request.prohibited_symbols if item.strip()
            ),
            prohibited_sectors=frozenset(
                item.strip().casefold() for item in request.prohibited_sectors if item.strip()
            ),
            prohibited_countries=frozenset(
                item.strip().casefold() for item in request.prohibited_countries if item.strip()
            ),
            sector_max_weights={
                key.strip(): value for key, value in request.sector_max_weights.items()
            },
            country_max_weights={
                key.strip(): value for key, value in request.country_max_weights.items()
            },
            age=request.age,
            residence_country=_country(request.residence_country),
            tax_residency=_country(request.tax_residency),
            monthly_surplus=monthly_surplus,
            emergency_reserve_target=emergency_reserve_target,
            unfunded_emergency_reserve=unfunded_reserve,
            investable_assets_after_reserve=investable_after_reserve,
            dependents=request.dependents,
            income_stability=IncomeStability(request.income_stability),
            investment_experience=InvestmentExperience(request.investment_experience),
            short_selling_allowed=request.short_selling_allowed,
            leverage_policy=LeveragePolicy(request.leverage_policy),
            preferred_styles=tuple(
                item.strip().casefold() for item in request.preferred_styles if item.strip()
            ),
            prefers_dividends=request.prefers_dividends,
            requires_fixed_income=request.requires_fixed_income,
            risk_assessment=assessment,
            tax_policy=request.tax_policy,
            profile_as_of=request.profile_as_of,
        )

    def create_from_file(self, path: Path | str) -> InvestorProfile:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("investor profile file must contain a JSON object")
        return self.create_from_mapping(payload)

    def create_from_mapping(self, payload: Mapping) -> InvestorProfile:
        values = dict(payload)
        for key, enum_type in (
            ("risk_tolerance", RiskTolerance),
            ("income_stability", IncomeStability),
            ("investment_experience", InvestmentExperience),
            ("leverage_policy", LeveragePolicy),
        ):
            if values.get(key) is not None:
                values[key] = enum_type(values[key])
        if isinstance(values.get("profile_as_of"), str):
            values["profile_as_of"] = date.fromisoformat(values["profile_as_of"])
        tax_policy = values.get("tax_policy")
        if isinstance(tax_policy, Mapping):
            tax_values = dict(tax_policy)
            if isinstance(tax_values.get("rules_as_of"), str):
                tax_values["rules_as_of"] = date.fromisoformat(tax_values["rules_as_of"])
            values["tax_policy"] = TaxPolicy(**tax_values)
        return self.create(InvestorProfileRequest(**values))


def _assess_risk(request: InvestorProfileRequest) -> RiskProfileAssessment:
    capacity, capacity_score, capacity_reasons = _risk_capacity(request)
    willingness = (
        RiskTolerance(request.risk_tolerance)
        if request.risk_tolerance is not None
        else _risk_from_drawdown(request.max_drawdown)
    )
    need = _risk_need(request)
    effective = min((capacity, willingness, need), key=_RISK_ORDER.__getitem__)
    reasons = capacity_reasons + (
        f"Willingness maps a {request.max_drawdown:.0%} drawdown limit to {willingness.value}.",
        f"Objectives and horizon imply {need.value} required risk.",
        f"Effective risk is the most conservative dimension: {effective.value}.",
    )
    return RiskProfileAssessment(
        capacity=capacity,
        willingness=willingness,
        need=need,
        effective=effective,
        capacity_score=capacity_score,
        reasons=reasons,
    )


def _risk_capacity(request: InvestorProfileRequest):
    if not _has_financial_context(request):
        fallback = (
            RiskTolerance(request.risk_tolerance)
            if request.risk_tolerance is not None
            else RiskTolerance.MODERATE
        )
        return fallback, 0, ("Financial capacity inputs were not supplied; used fallback.",)
    score = 0
    reasons = []
    if request.age is not None and request.age <= 35:
        score += 2
        reasons.append("Age supports a long recovery period.")
    elif request.age is not None and request.age <= 55:
        score += 1
        reasons.append("Age supports a moderate recovery period.")
    if request.horizon_years >= 10:
        score += 2
        reasons.append("Investment horizon is at least ten years.")
    elif request.horizon_years >= 5:
        score += 1
        reasons.append("Investment horizon is at least five years.")
    if request.dependents == 0:
        score += 1
        reasons.append("There are no financial dependents.")
    if IncomeStability(request.income_stability) == IncomeStability.STABLE:
        score += 1
        reasons.append("Employment income is stable.")
    if request.monthly_expenses and request.liquid_net_worth is not None:
        coverage = request.liquid_net_worth / request.monthly_expenses
        if coverage >= 24:
            score += 2
            reasons.append("Liquid assets cover at least 24 months of expenses.")
        elif coverage >= 6:
            score += 1
            reasons.append("Liquid assets cover at least six months of expenses.")
    surplus = _monthly_surplus(request)
    if surplus is not None and request.monthly_net_income:
        surplus_ratio = surplus / request.monthly_net_income
        if surplus_ratio >= 0.40:
            score += 2
            reasons.append("Monthly savings capacity is at least 40% of net income.")
        elif surplus_ratio >= 0.15:
            score += 1
            reasons.append("Monthly savings capacity is at least 15% of net income.")
    if score >= 8:
        capacity = RiskTolerance.AGGRESSIVE
    elif score >= 4:
        capacity = RiskTolerance.MODERATE
    else:
        capacity = RiskTolerance.CONSERVATIVE
    return capacity, score, tuple(reasons)


def _risk_need(request: InvestorProfileRequest):
    objectives = " ".join(request.objectives).casefold()
    if any(term in objectives for term in ("preservation", "preservacion", "liquidity")):
        return RiskTolerance.CONSERVATIVE
    if request.horizon_years >= 10 and any(
        term in objectives for term in ("growth", "crecimiento", "capital appreciation")
    ):
        return RiskTolerance.MODERATE
    return RiskTolerance.MODERATE


def _risk_from_drawdown(max_drawdown: float):
    if max_drawdown <= 0.15:
        return RiskTolerance.CONSERVATIVE
    if max_drawdown <= 0.30:
        return RiskTolerance.MODERATE
    return RiskTolerance.AGGRESSIVE


def _has_financial_context(request: InvestorProfileRequest):
    return any(
        value is not None
        for value in (
            request.age,
            request.monthly_net_income,
            request.monthly_expenses,
            request.liquid_net_worth,
            request.portfolio_funding,
        )
    )


def _monthly_surplus(request: InvestorProfileRequest):
    if request.monthly_net_income is None or request.monthly_expenses is None:
        return None
    return request.monthly_net_income - request.monthly_expenses


def _emergency_reserve_target(request: InvestorProfileRequest):
    if request.monthly_expenses is None:
        return None
    return request.monthly_expenses * request.emergency_fund_months_target


def _country(value: str | None):
    return value.strip().upper() if value is not None else None
