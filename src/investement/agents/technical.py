from itertools import pairwise
from math import sqrt
from statistics import mean, stdev

from investement.agents.models import AssetDataSnapshot, TechnicalAnalysis
from investement.orchestration import AgentFinding, EvidenceReference


class TechnicalAgent:
    name = "technical"

    def __init__(
        self,
        short_window: int = 20,
        long_window: int = 50,
        momentum_window: int = 20,
        rsi_window: int = 14,
        annualization_factor: int = 252,
    ) -> None:
        if min(short_window, long_window, momentum_window, rsi_window) <= 1:
            raise ValueError("technical windows must be greater than one")
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        if annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")
        self._short_window = short_window
        self._long_window = long_window
        self._momentum_window = momentum_window
        self._rsi_window = rsi_window
        self._annualization_factor = annualization_factor

    def analyze(self, snapshot: AssetDataSnapshot) -> TechnicalAnalysis:
        closes = tuple(float(bar.adjusted_close) for bar in snapshot.bars)
        required = max(self._long_window, self._momentum_window + 1, self._rsi_window + 1)
        if len(closes) < required:
            raise ValueError(f"technical analysis requires at least {required} price bars")
        returns = tuple(current / previous - 1 for previous, current in pairwise(closes))
        short_average = mean(closes[-self._short_window :])
        long_average = mean(closes[-self._long_window :])
        momentum = closes[-1] / closes[-self._momentum_window - 1] - 1
        rsi = _rsi(closes, self._rsi_window)
        macd_series = tuple(
            fast - slow for fast, slow in zip(_ema(closes, 12), _ema(closes, 26), strict=True)
        )
        macd_signal_series = _ema(macd_series, 9)
        annual_volatility = stdev(returns) * sqrt(self._annualization_factor)
        drawdown = _max_drawdown(closes)
        score = _technical_score(
            short_average,
            long_average,
            momentum,
            rsi,
            macd_series[-1],
            macd_signal_series[-1],
            annual_volatility,
            drawdown,
        )
        risks = []
        if annual_volatility > 0.40:
            risks.append("Annualized volatility is above 40%")
        if drawdown > 0.20:
            risks.append("Observed drawdown is above 20%")
        latest_bar = snapshot.bars[-1]
        evidence = (
            EvidenceReference(
                source=latest_bar.provenance.source,
                reference=(
                    latest_bar.provenance.raw_reference
                    or f"{snapshot.symbol}:{latest_bar.timestamp.isoformat()}"
                ),
                observed_at=latest_bar.provenance.available_at,
            ),
        )
        confidence = min(0.95, 0.55 + len(closes) / 500)
        finding = AgentFinding(
            agent=self.name,
            subject=snapshot.symbol,
            score=score,
            confidence=confidence,
            thesis=(
                f"Trend SMA {short_average:.2f}/{long_average:.2f}, momentum "
                f"{momentum:.1%}, RSI {rsi:.1f}, volatility {annual_volatility:.1%}."
            ),
            evidence=evidence,
            risks=tuple(risks),
            invalidation_conditions=(
                "Short-term trend crosses against the long-term trend",
                "Volatility or drawdown breaches the investor profile",
            ),
        )
        return TechnicalAnalysis(
            short_moving_average=short_average,
            long_moving_average=long_average,
            momentum=momentum,
            rsi=rsi,
            macd=macd_series[-1],
            macd_signal=macd_signal_series[-1],
            annual_volatility=annual_volatility,
            max_drawdown=drawdown,
            finding=finding,
        )


def _technical_score(
    short_average: float,
    long_average: float,
    momentum: float,
    rsi: float,
    macd: float,
    macd_signal: float,
    volatility: float,
    drawdown: float,
) -> float:
    trend = 0.35 if short_average >= long_average else -0.35
    momentum_component = 0.25 * _clamp(momentum / 0.15)
    rsi_component = 0.10 * _clamp((55.0 - rsi) / 25.0)
    macd_component = 0.20 if macd >= macd_signal else -0.20
    risk_penalty = 0.10 * _clamp(max(volatility - 0.30, 0.0) / 0.30)
    risk_penalty += 0.10 * _clamp(max(drawdown - 0.15, 0.0) / 0.25)
    return _clamp(trend + momentum_component + rsi_component + macd_component - risk_penalty)


def _ema(values: tuple[float, ...], period: int) -> tuple[float, ...]:
    alpha = 2.0 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return tuple(result)


def _rsi(closes: tuple[float, ...], period: int) -> float:
    changes = tuple(current - previous for previous, current in pairwise(closes))
    recent = changes[-period:]
    average_gain = mean(max(change, 0.0) for change in recent)
    average_loss = mean(max(-change, 0.0) for change in recent)
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _max_drawdown(closes: tuple[float, ...]) -> float:
    peak = closes[0]
    maximum = 0.0
    for close in closes:
        peak = max(peak, close)
        maximum = max(maximum, (peak - close) / peak)
    return maximum


def _clamp(value: float) -> float:
    return max(-1.0, min(float(value), 1.0))
