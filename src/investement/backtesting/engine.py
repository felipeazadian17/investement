from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from investement.backtesting.metrics import PerformanceMetrics, calculate_metrics


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1.0
    commission_bps: float = 1.0
    slippage_bps: float = 4.0
    signal_delay_bars: int = 1
    periods_per_year: int = 252
    annual_risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        if not isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive and finite")
        if self.commission_bps < 0 or self.slippage_bps < 0:
            raise ValueError("cost assumptions cannot be negative")
        if self.signal_delay_bars < 1:
            raise ValueError("signal_delay_bars must be at least 1 to prevent look-ahead")
        if self.periods_per_year <= 0:
            raise ValueError("periods_per_year must be positive")


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: Sequence[float]
    period_returns: Sequence[float]
    turnover: float
    transaction_cost: float
    metrics: PerformanceMetrics


def run_weight_backtest(
    prices: Mapping[str, Sequence[float]],
    target_weights: Mapping[str, Sequence[float]],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    assets = tuple(prices)
    if not assets or set(assets) != set(target_weights):
        raise ValueError("prices and target_weights must contain the same assets")
    lengths = {len(prices[asset]) for asset in assets}
    lengths.update(len(target_weights[asset]) for asset in assets)
    if len(lengths) != 1 or next(iter(lengths)) < 2:
        raise ValueError("all price and weight series must share a length of at least two")
    observations = next(iter(lengths))
    _validate_inputs(assets, observations, prices, target_weights)

    cost_rate = (config.commission_bps + config.slippage_bps) / 10_000.0
    previous_weights = {asset: 0.0 for asset in assets}
    equity = config.initial_capital
    equity_curve = [equity]
    period_returns = []
    total_turnover = 0.0
    total_cost = 0.0

    for index in range(1, observations):
        signal_index = index - config.signal_delay_bars
        desired = {
            asset: (float(target_weights[asset][signal_index]) if signal_index >= 0 else 0.0)
            for asset in assets
        }
        previous_cash = 1.0 - sum(previous_weights.values())
        desired_cash = 1.0 - sum(desired.values())
        turnover = 0.5 * (
            sum(abs(desired[asset] - previous_weights[asset]) for asset in assets)
            + abs(desired_cash - previous_cash)
        )
        asset_return = {
            asset: float(prices[asset][index]) / float(prices[asset][index - 1]) - 1
            for asset in assets
        }
        gross_return = sum(desired[asset] * asset_return[asset] for asset in assets)
        cost = turnover * cost_rate
        net_return = gross_return - cost
        if net_return <= -1:
            raise RuntimeError("portfolio lost all capital in one period")
        equity *= 1 + net_return
        period_returns.append(net_return)
        equity_curve.append(equity)
        total_turnover += turnover
        total_cost += cost
        previous_weights = desired

    metrics = calculate_metrics(
        period_returns,
        periods_per_year=config.periods_per_year,
        annual_risk_free_rate=config.annual_risk_free_rate,
    )
    return BacktestResult(
        equity_curve=tuple(equity_curve),
        period_returns=tuple(period_returns),
        turnover=total_turnover,
        transaction_cost=total_cost,
        metrics=metrics,
    )


def _validate_inputs(
    assets: Sequence[str],
    observations: int,
    prices: Mapping[str, Sequence[float]],
    target_weights: Mapping[str, Sequence[float]],
) -> None:
    for asset in assets:
        if not asset.strip():
            raise ValueError("asset symbols cannot be empty")
        if any(not isfinite(float(price)) or price <= 0 for price in prices[asset]):
            raise ValueError("prices must be positive and finite")
        if any(
            not isfinite(float(weight)) or not 0 <= weight <= 1 for weight in target_weights[asset]
        ):
            raise ValueError("target weights must be finite and between 0 and 1")
    for index in range(observations):
        if sum(float(target_weights[asset][index]) for asset in assets) > 1 + 1e-9:
            raise ValueError("target weights cannot use leverage")
