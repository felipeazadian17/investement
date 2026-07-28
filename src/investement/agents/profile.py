from investement.agents.models import (
    InvestorProfile,
    InvestorProfileRequest,
    RiskTolerance,
)

_DEFAULT_VOLATILITY_LIMITS = {
    RiskTolerance.CONSERVATIVE: 0.20,
    RiskTolerance.MODERATE: 0.35,
    RiskTolerance.AGGRESSIVE: 0.55,
}


class InvestorProfileAgent:
    name = "investor-profile"

    def create(self, request: InvestorProfileRequest) -> InvestorProfile:
        risk_tolerance = RiskTolerance(request.risk_tolerance)
        max_volatility = request.max_annual_volatility
        if max_volatility is None:
            max_volatility = _DEFAULT_VOLATILITY_LIMITS[risk_tolerance]
        return InvestorProfile(
            objectives=tuple(item.strip() for item in request.objectives),
            horizon_years=request.horizon_years,
            base_currency=request.base_currency.strip().upper(),
            risk_tolerance=risk_tolerance,
            min_cash_weight=request.min_cash_weight,
            max_position_weight=request.max_position_weight,
            max_drawdown=request.max_drawdown,
            max_annual_volatility=max_volatility,
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
        )
