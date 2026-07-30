from collections.abc import Mapping
from math import ceil, sqrt
from statistics import mean, stdev

from investement.portfolio.constraints import project_weights, validate_weights
from investement.portfolio.models import AllocationResult, PortfolioRequest


class RobustPortfolioOptimizer:
    """Common optimizer facade with deterministic constrained fallback."""

    def optimize(
        self,
        request: PortfolioRequest,
        backend: str = "inverse_volatility",
    ) -> AllocationResult:
        warnings = []
        selected_backend = backend
        try:
            if backend == "inverse_volatility":
                scores = _inverse_volatility_scores(request)
            elif backend == "pypfopt":
                scores = _pypfopt_scores(request)
            elif backend == "riskfolio":
                scores = _riskfolio_scores(request)
            else:
                raise ValueError(f"unknown optimizer backend: {backend}")
        except (ImportError, ModuleNotFoundError) as exc:
            selected_backend = "inverse_volatility"
            warnings.append(f"{backend} unavailable; used inverse-volatility fallback")
            warnings.append(str(exc))
            scores = _inverse_volatility_scores(request)

        weights = dict(project_weights(scores, request.constraints, request.metadata))
        expected_returns, covariance = _moments(request)
        annual_volatility = _portfolio_volatility(weights, covariance)
        if (
            request.constraints.max_annual_volatility is not None
            and annual_volatility > request.constraints.max_annual_volatility
        ):
            scale = request.constraints.max_annual_volatility / annual_volatility
            weights = {asset: weight * scale for asset, weight in weights.items()}
            annual_volatility = _portfolio_volatility(weights, covariance)
            warnings.append(
                "risky allocation scaled into cash to satisfy the annual volatility limit"
            )
        violations = validate_weights(weights, request.constraints, request.metadata)
        if violations:
            raise RuntimeError(f"constraint projection failed: {'; '.join(violations)}")
        expected = sum(weights[asset] * expected_returns[asset] for asset in weights)
        portfolio_returns = _portfolio_returns(request, weights)
        var_95, expected_shortfall_95 = _historical_tail_risk(portfolio_returns)
        risk_contributions = _risk_contributions(weights, covariance)
        observations = len(portfolio_returns)
        if not request.return_dates:
            warnings.append("return dates unavailable; cross-asset alignment cannot be audited")
        if observations < 60:
            warnings.append("fewer than 60 aligned return observations; risk estimates are fragile")
        elif observations < 252:
            warnings.append("fewer than 252 aligned return observations; full-cycle coverage is limited")
        if observations <= len(weights):
            warnings.append("observations do not exceed asset count; sample covariance is singular")
        turnover = _turnover(weights, request.current_weights)
        return AllocationResult(
            weights=weights,
            cash_weight=max(0.0, 1.0 - sum(weights.values())),
            backend=selected_backend,
            expected_annual_return=expected,
            annual_volatility=annual_volatility,
            warnings=tuple(warnings),
            observations=observations,
            historical_var_95=var_95,
            historical_expected_shortfall_95=expected_shortfall_95,
            historical_max_drawdown=_max_drawdown(portfolio_returns),
            effective_number_of_assets=_effective_number(weights),
            turnover=turnover,
            risk_contributions=risk_contributions,
            group_exposures=_group_exposures(weights, request.metadata),
        )


def _inverse_volatility_scores(request: PortfolioRequest) -> Mapping[str, float]:
    scores = {}
    for asset, values in request.returns.items():
        volatility = stdev(float(value) for value in values)
        scores[asset] = 1.0 / max(volatility, 1e-12)
    return scores


def _pypfopt_scores(request: PortfolioRequest) -> Mapping[str, float]:
    import pandas as pd
    from pypfopt import EfficientFrontier, risk_models

    frame = pd.DataFrame(request.returns, index=request.return_dates or None)
    expected = frame.mean() * request.annualization_factor
    covariance = risk_models.CovarianceShrinkage(
        frame,
        returns_data=True,
        frequency=request.annualization_factor,
    ).ledoit_wolf()
    maximum = max(
        [request.constraints.max_weight] + list(request.constraints.asset_max_weights.values())
    )
    frontier = EfficientFrontier(expected, covariance, weight_bounds=(0, maximum))
    frontier.min_volatility()
    return {asset: max(float(weight), 0.0) for asset, weight in frontier.clean_weights().items()}


def _riskfolio_scores(request: PortfolioRequest) -> Mapping[str, float]:
    import pandas as pd
    import riskfolio as rp

    portfolio = rp.Portfolio(
        returns=pd.DataFrame(request.returns, index=request.return_dates or None)
    )
    portfolio.assets_stats(method_mu="hist", method_cov="ledoit")
    result = portfolio.rp_optimization(model="Classic", rm="MV", hist=True, rf=0, b=None)
    if result is None or result.empty:
        raise RuntimeError("Riskfolio returned no allocation")
    column = result.columns[0]
    return {asset: max(float(result.loc[asset, column]), 0.0) for asset in request.returns}


def _moments(request: PortfolioRequest) -> tuple:
    assets = tuple(request.returns)
    annualizer = request.annualization_factor
    expected = {
        asset: mean(float(value) for value in request.returns[asset]) * annualizer
        for asset in assets
    }
    covariance = {asset: {} for asset in assets}
    for left in assets:
        for right in assets:
            covariance[left][right] = (
                _sample_covariance(request.returns[left], request.returns[right]) * annualizer
            )
    return expected, covariance


def _sample_covariance(left: object, right: object) -> float:
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)
    left_mean = mean(left_values)
    right_mean = mean(right_values)
    return sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_values, right_values)
    ) / (len(left_values) - 1)


def _portfolio_volatility(
    weights: Mapping[str, float],
    covariance: Mapping[str, Mapping[str, float]],
) -> float:
    variance = sum(
        weights[left] * weights[right] * covariance[left][right]
        for left in weights
        for right in weights
    )
    return sqrt(max(variance, 0.0))


def _portfolio_returns(
    request: PortfolioRequest,
    weights: Mapping[str, float],
) -> tuple[float, ...]:
    return tuple(
        sum(weights[asset] * float(request.returns[asset][index]) for asset in weights)
        for index in range(len(next(iter(request.returns.values()))))
    )


def _historical_tail_risk(
    returns: tuple[float, ...],
    confidence: float = 0.95,
) -> tuple[float, float]:
    tail_count = max(1, ceil((1.0 - confidence) * len(returns)))
    tail = tuple(sorted(returns)[:tail_count])
    return max(0.0, -tail[-1]), max(0.0, -mean(tail))


def _max_drawdown(returns: tuple[float, ...]) -> float:
    wealth = 1.0
    peak = 1.0
    maximum = 0.0
    for value in returns:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        maximum = max(maximum, (peak - wealth) / peak)
    return maximum


def _effective_number(weights: Mapping[str, float]) -> float:
    invested = sum(weights.values())
    if invested <= 0:
        return 0.0
    normalized = (weight / invested for weight in weights.values())
    concentration = sum(weight * weight for weight in normalized)
    return 1.0 / concentration if concentration > 0 else 0.0


def _risk_contributions(
    weights: Mapping[str, float],
    covariance: Mapping[str, Mapping[str, float]],
) -> Mapping[str, float]:
    variance = _portfolio_volatility(weights, covariance) ** 2
    if variance <= 0:
        return {asset: 0.0 for asset in weights}
    return {
        asset: weights[asset]
        * sum(covariance[asset][other] * weights[other] for other in weights)
        / variance
        for asset in weights
    }


def _turnover(
    weights: Mapping[str, float],
    current_weights: Mapping[str, float],
) -> float | None:
    if not current_weights:
        return None
    assets = set(weights) | set(current_weights)
    current_cash = max(0.0, 1.0 - sum(current_weights.values()))
    target_cash = max(0.0, 1.0 - sum(weights.values()))
    return 0.5 * (
        sum(abs(weights.get(asset, 0.0) - current_weights.get(asset, 0.0)) for asset in assets)
        + abs(target_cash - current_cash)
    )


def _group_exposures(
    weights: Mapping[str, float],
    metadata: Mapping[str, object],
) -> Mapping[str, Mapping[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for attribute in ("sector", "country", "asset_class", "currency"):
        groups: dict[str, float] = {}
        for asset, weight in weights.items():
            value = getattr(metadata.get(asset), attribute, None)
            if value:
                groups[str(value)] = groups.get(str(value), 0.0) + weight
        result[attribute] = groups
    return result
