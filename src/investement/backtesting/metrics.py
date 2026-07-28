from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean, stdev


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    observations: int


def calculate_metrics(
    returns: Sequence[float],
    periods_per_year: int = 252,
    annual_risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    if not returns:
        raise ValueError("returns cannot be empty")
    values = tuple(float(value) for value in returns)
    if any(not isfinite(value) or value <= -1 for value in values):
        raise ValueError("returns must be finite and greater than -1")

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)

    total_return = equity - 1
    annualized_return = equity ** (periods_per_year / len(values)) - 1
    volatility = stdev(values) * sqrt(periods_per_year) if len(values) > 1 else 0.0
    risk_free_period = annual_risk_free_rate / periods_per_year
    excess_mean = mean(value - risk_free_period for value in values)
    sharpe = excess_mean * periods_per_year / volatility if volatility > 0 else 0.0
    downside = [min(value - risk_free_period, 0.0) for value in values]
    downside_deviation = sqrt(sum(value * value for value in downside) / len(values))
    annual_downside = downside_deviation * sqrt(periods_per_year)
    sortino = excess_mean * periods_per_year / annual_downside if annual_downside > 0 else 0.0
    calmar = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
    return PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_drawdown,
        calmar_ratio=calmar,
        observations=len(values),
    )
