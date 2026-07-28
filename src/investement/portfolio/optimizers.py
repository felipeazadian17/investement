from collections.abc import Mapping
from math import sqrt
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

        weights = project_weights(scores, request.constraints, request.metadata)
        violations = validate_weights(weights, request.constraints, request.metadata)
        if violations:
            raise RuntimeError(f"constraint projection failed: {'; '.join(violations)}")
        expected_returns, covariance = _moments(request)
        expected = sum(weights[asset] * expected_returns[asset] for asset in weights)
        variance = sum(
            weights[left] * weights[right] * covariance[left][right]
            for left in weights
            for right in weights
        )
        return AllocationResult(
            weights=weights,
            cash_weight=request.constraints.min_cash,
            backend=selected_backend,
            expected_annual_return=expected,
            annual_volatility=sqrt(max(variance, 0.0)),
            warnings=tuple(warnings),
        )


def _inverse_volatility_scores(request: PortfolioRequest) -> Mapping[str, float]:
    scores = {}
    for asset, values in request.returns.items():
        volatility = stdev(float(value) for value in values)
        scores[asset] = 1.0 / max(volatility, 1e-12)
    return scores


def _pypfopt_scores(request: PortfolioRequest) -> Mapping[str, float]:
    import pandas as pd
    from pypfopt import EfficientFrontier

    frame = pd.DataFrame(request.returns)
    expected = frame.mean() * request.annualization_factor
    covariance = frame.cov() * request.annualization_factor
    maximum = max(
        [request.constraints.max_weight] + list(request.constraints.asset_max_weights.values())
    )
    frontier = EfficientFrontier(expected, covariance, weight_bounds=(0, maximum))
    frontier.min_volatility()
    return {asset: max(float(weight), 0.0) for asset, weight in frontier.clean_weights().items()}


def _riskfolio_scores(request: PortfolioRequest) -> Mapping[str, float]:
    import pandas as pd
    import riskfolio as rp

    portfolio = rp.Portfolio(returns=pd.DataFrame(request.returns))
    portfolio.assets_stats(method_mu="hist", method_cov="hist")
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
