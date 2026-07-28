from collections.abc import Mapping, Sequence


class QuantStatsMetrics:
    name = "quantstats"

    def compute(self, returns: Sequence[float], periods_per_year: int = 252) -> Mapping[str, float]:
        try:
            import pandas as pd
            import quantstats as qs
        except ImportError as exc:
            raise RuntimeError(
                "QuantStats is optional; install with `pip install -e '.[analytics]'`"
            ) from exc
        values = tuple(float(value) for value in returns)
        series = pd.Series(
            values,
            index=pd.date_range("2000-01-03", periods=len(values), freq="B"),
        )
        return {
            "cagr": float(qs.stats.cagr(series, periods=periods_per_year)),
            "sharpe": float(qs.stats.sharpe(series, periods=periods_per_year)),
            "sortino": float(qs.stats.sortino(series, periods=periods_per_year)),
            "max_drawdown": float(qs.stats.max_drawdown(series)),
        }


class VectorbtSingleAsset:
    name = "vectorbt"

    def run(
        self,
        prices: Sequence[float],
        entries: Sequence[bool],
        exits: Sequence[bool],
        fees: float = 0.0001,
        slippage: float = 0.0004,
        initial_cash: float = 100_000.0,
    ) -> Mapping[str, object]:
        if not (len(prices) == len(entries) == len(exits)):
            raise ValueError("prices, entries and exits must have equal length")
        try:
            import pandas as pd
            import vectorbt as vbt
        except ImportError as exc:
            raise RuntimeError(
                "vectorbt is optional; install with `pip install -e '.[analytics]'`"
            ) from exc
        portfolio = vbt.Portfolio.from_signals(
            pd.Series(prices, dtype=float),
            entries=pd.Series(entries, dtype=bool).shift(1, fill_value=False),
            exits=pd.Series(exits, dtype=bool).shift(1, fill_value=False),
            fees=fees,
            slippage=slippage,
            init_cash=initial_cash,
            freq="1D",
        )
        return dict(portfolio.stats())
