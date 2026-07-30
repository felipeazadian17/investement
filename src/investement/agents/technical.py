from dataclasses import asdict, dataclass
from itertools import pairwise
from math import sqrt
from statistics import mean, stdev

from investement.agents.models import (
    AssetDataSnapshot,
    TechnicalAnalysis,
    TechnicalRegime,
    TechnicalTimingAction,
    TechnicalTimingSignal,
)
from investement.orchestration import AgentFinding, EvidenceReference


@dataclass(frozen=True)
class TechnicalParameters:
    short_window: int = 50
    long_window: int = 200
    trend_band: float = 0.01
    momentum_window: int = 252
    momentum_skip: int = 21
    medium_momentum_window: int = 63
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_window: int = 14
    volume_window: int = 20
    breakout_window: int = 63
    volatility_window: int = 63
    drawdown_window: int = 252
    annualization_factor: int = 252
    timing_valid_bars: int = 5

    def __post_init__(self) -> None:
        windows = (
            self.short_window,
            self.long_window,
            self.momentum_window,
            self.medium_momentum_window,
            self.rsi_window,
            self.macd_fast,
            self.macd_slow,
            self.macd_signal,
            self.atr_window,
            self.volume_window,
            self.breakout_window,
            self.volatility_window,
            self.drawdown_window,
            self.timing_valid_bars,
        )
        if min(windows) <= 1:
            raise ValueError("technical windows must be greater than one")
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("MACD fast period must be smaller than its slow period")
        if not 0 <= self.momentum_skip < self.momentum_window:
            raise ValueError("momentum_skip must be below momentum_window")
        if not 0 <= self.trend_band <= 0.10:
            raise ValueError("trend_band must be between zero and 10%")
        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")

    @property
    def minimum_bars(self) -> int:
        return max(
            self.long_window + 1,
            self.momentum_window + 1,
            self.medium_momentum_window + 1,
            self.rsi_window + 2,
            self.macd_slow + self.macd_signal + 1,
            self.atr_window + 2,
            self.volume_window + 1,
            self.breakout_window + 1,
            self.volatility_window + 1,
            self.drawdown_window,
        )


class TechnicalAgent:
    name = "technical"

    def __init__(self, parameters: TechnicalParameters | None = None) -> None:
        self._parameters = parameters or TechnicalParameters()

    def analyze(self, snapshot: AssetDataSnapshot) -> TechnicalAnalysis:
        _validate_bars(snapshot)
        parameters = self._parameters
        if len(snapshot.bars) < parameters.minimum_bars:
            raise ValueError(
                f"technical analysis requires at least {parameters.minimum_bars} daily bars"
            )

        closes = tuple(float(bar.adjusted_close) for bar in snapshot.bars)
        returns = tuple(current / previous - 1 for previous, current in pairwise(closes))
        short_average = mean(closes[-parameters.short_window :])
        long_average = mean(closes[-parameters.long_window :])
        previous_short_average = mean(
            closes[-parameters.short_window - 1 : -1]
        )
        previous_long_average = mean(closes[-parameters.long_window - 1 : -1])
        trend_spread = short_average / long_average - 1
        previous_trend_spread = previous_short_average / previous_long_average - 1
        price_to_long_average = closes[-1] / long_average - 1
        regime = _trend_regime(trend_spread, price_to_long_average, parameters.trend_band)

        momentum = (
            closes[-parameters.momentum_skip - 1]
            / closes[-parameters.momentum_window - 1]
            - 1
        )
        medium_momentum = closes[-1] / closes[-parameters.medium_momentum_window - 1] - 1
        rsi_series = _rsi_series(closes, parameters.rsi_window)
        rsi = _required_value(rsi_series[-1], "RSI")
        previous_rsi = _required_value(rsi_series[-2], "previous RSI")
        macd, macd_signal, macd_histogram, previous_macd_histogram = _macd(
            closes,
            parameters.macd_fast,
            parameters.macd_slow,
            parameters.macd_signal,
        )
        normalized_atr = _normalized_atr(snapshot, parameters.atr_window)
        volume_ratio = _volume_ratio(snapshot, parameters.volume_window)
        annual_volatility = (
            stdev(returns[-parameters.volatility_window :])
            * sqrt(parameters.annualization_factor)
        )
        max_drawdown, current_drawdown = _drawdowns(
            closes[-parameters.drawdown_window :]
        )

        prior_high = max(closes[-parameters.breakout_window - 1 : -1])
        prior_low = min(closes[-parameters.breakout_window - 1 : -1])
        breakout_up = closes[-1] > prior_high and (volume_ratio or 0.0) >= 1.0
        breakout_down = closes[-1] < prior_low
        bullish_cross = (
            trend_spread >= parameters.trend_band
            and previous_trend_spread < parameters.trend_band
        )
        pullback_recovery = (
            regime is TechnicalRegime.BULLISH
            and previous_rsi < 45 <= rsi
            and macd_histogram > previous_macd_histogram
        )

        score = _technical_score(
            regime=regime,
            momentum=momentum,
            medium_momentum=medium_momentum,
            rsi=rsi,
            macd_histogram=macd_histogram,
            previous_macd_histogram=previous_macd_histogram,
            volume_ratio=volume_ratio,
            volatility=annual_volatility,
            current_drawdown=current_drawdown,
            normalized_atr=normalized_atr,
        )
        stale_days = max(0, (snapshot.as_of.date() - snapshot.bars[-1].timestamp.date()).days)
        confidence = _technical_confidence(
            bar_count=len(closes),
            minimum_bars=parameters.minimum_bars,
            regime=regime,
            momentum=momentum,
            medium_momentum=medium_momentum,
            macd_histogram=macd_histogram,
            volume_available=volume_ratio is not None,
            stale_days=stale_days,
        )
        timing = _timing_signal(
            snapshot=snapshot,
            parameters=parameters,
            regime=regime,
            score=score,
            confidence=confidence,
            momentum=momentum,
            medium_momentum=medium_momentum,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            breakout_up=breakout_up,
            breakout_down=breakout_down,
            bullish_cross=bullish_cross,
            pullback_recovery=pullback_recovery,
        )

        risks = _technical_risks(
            len(closes),
            annual_volatility,
            max_drawdown,
            current_drawdown,
            normalized_atr,
            volume_ratio,
            stale_days,
        )
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
        finding = AgentFinding(
            agent=self.name,
            subject=snapshot.symbol,
            score=score,
            confidence=confidence,
            thesis=(
                f"Regime {regime.value}; SMA {parameters.short_window}/"
                f"{parameters.long_window} spread {trend_spread:.1%}; momentum 12-1 "
                f"{momentum:.1%}; momentum 3m {medium_momentum:.1%}; RSI {rsi:.1f}; "
                f"timing {timing.action.value}."
            ),
            evidence=evidence,
            risks=risks,
            invalidation_conditions=timing.invalidation_conditions,
        )
        return TechnicalAnalysis(
            short_moving_average=short_average,
            long_moving_average=long_average,
            momentum=momentum,
            medium_momentum=medium_momentum,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            normalized_atr=normalized_atr,
            volume_ratio=volume_ratio,
            annual_volatility=annual_volatility,
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            trend_regime=regime,
            timing=timing,
            parameters=asdict(parameters),
            finding=finding,
        )


def _validate_bars(snapshot: AssetDataSnapshot) -> None:
    timestamps = tuple(bar.timestamp for bar in snapshot.bars)
    if any(current <= previous for previous, current in pairwise(timestamps)):
        raise ValueError("technical analysis requires strictly increasing price bars")
    intervals = {
        str(bar.provenance.metadata.get("interval", "")).strip().casefold()
        for bar in snapshot.bars
        if bar.provenance.metadata.get("interval")
    }
    if intervals and not intervals <= {"1d", "1day", "daily"}:
        raise ValueError("baseline technical parameters require daily bars")


def _trend_regime(
    trend_spread: float,
    price_to_long_average: float,
    band: float,
) -> TechnicalRegime:
    if trend_spread >= band and price_to_long_average >= band:
        return TechnicalRegime.BULLISH
    if trend_spread <= -band and price_to_long_average <= -band:
        return TechnicalRegime.BEARISH
    return TechnicalRegime.NEUTRAL


def _technical_score(
    *,
    regime: TechnicalRegime,
    momentum: float,
    medium_momentum: float,
    rsi: float,
    macd_histogram: float,
    previous_macd_histogram: float,
    volume_ratio: float | None,
    volatility: float,
    current_drawdown: float,
    normalized_atr: float,
) -> float:
    regime_direction = {
        TechnicalRegime.BULLISH: 1.0,
        TechnicalRegime.NEUTRAL: 0.0,
        TechnicalRegime.BEARISH: -1.0,
    }[regime]
    trend_component = 0.35 * regime_direction
    momentum_component = 0.15 * _clamp(momentum / 0.30)
    momentum_component += 0.10 * _clamp(medium_momentum / 0.15)
    macd_component = 0.10 * _sign(macd_histogram)
    macd_component += 0.05 * _sign(macd_histogram - previous_macd_histogram)
    rsi_component = 0.10 * _rsi_regime_score(regime, rsi)
    volume_component = 0.0
    if volume_ratio is not None and regime_direction:
        volume_component = (
            0.05 * regime_direction * _clamp(max(volume_ratio - 1.0, 0.0))
        )
    risk_penalty = 0.04 * _clamp(max(volatility - 0.30, 0.0) / 0.30)
    risk_penalty += 0.03 * _clamp(max(current_drawdown - 0.10, 0.0) / 0.25)
    risk_penalty += 0.03 * _clamp(max(normalized_atr - 0.03, 0.0) / 0.05)
    return _clamp(
        trend_component
        + momentum_component
        + macd_component
        + rsi_component
        + volume_component
        - risk_penalty
    )


def _rsi_regime_score(regime: TechnicalRegime, rsi: float) -> float:
    if regime is TechnicalRegime.BULLISH:
        if 40 <= rsi <= 80:
            return 1.0
        return -0.50 if rsi < 40 else -0.25
    if regime is TechnicalRegime.BEARISH:
        if rsi < 40:
            return -1.0
        return -0.50 if rsi <= 60 else 0.25
    return _clamp((rsi - 50.0) / 30.0)


def _technical_confidence(
    *,
    bar_count: int,
    minimum_bars: int,
    regime: TechnicalRegime,
    momentum: float,
    medium_momentum: float,
    macd_histogram: float,
    volume_available: bool,
    stale_days: int,
) -> float:
    directions = (
        {
            TechnicalRegime.BULLISH: 1.0,
            TechnicalRegime.NEUTRAL: 0.0,
            TechnicalRegime.BEARISH: -1.0,
        }[regime],
        _sign(momentum),
        _sign(medium_momentum),
        _sign(macd_histogram),
    )
    agreement = abs(sum(directions)) / len(directions)
    history = min(max(bar_count - minimum_bars, 0) / 252, 1.0)
    confidence = 0.45 + 0.15 * history + 0.20 * agreement
    confidence += 0.05 if volume_available else 0.0
    confidence -= 0.15 if stale_days > 7 else 0.0
    return max(0.20, min(confidence, 0.85))


def _timing_signal(
    *,
    snapshot: AssetDataSnapshot,
    parameters: TechnicalParameters,
    regime: TechnicalRegime,
    score: float,
    confidence: float,
    momentum: float,
    medium_momentum: float,
    rsi: float,
    macd: float,
    macd_signal: float,
    breakout_up: bool,
    breakout_down: bool,
    bullish_cross: bool,
    pullback_recovery: bool,
) -> TechnicalTimingSignal:
    reasons: list[str] = []
    if regime is TechnicalRegime.BULLISH:
        triggers = []
        if breakout_up:
            triggers.append("63-day breakout confirmed by volume")
        if pullback_recovery:
            triggers.append("RSI pullback recovery with improving MACD histogram")
        if bullish_cross:
            triggers.append("50/200-day trend crossed above the confirmation band")
        if triggers and momentum > 0 and medium_momentum > 0 and rsi <= 80:
            action = TechnicalTimingAction.FAVOR_ENTRY
            reasons.extend(triggers)
            reasons.append("long and medium momentum are positive")
            strength = max(0.25, score)
        elif rsi > 80:
            action = TechnicalTimingAction.WAIT
            reasons.append("bullish trend is extended with RSI above 80")
            strength = max(0.0, score * 0.50)
        else:
            action = TechnicalTimingAction.HOLD
            reasons.append("bullish regime remains intact without a fresh entry trigger")
            strength = max(0.0, score)
    elif regime is TechnicalRegime.BEARISH:
        confirmations = []
        if momentum < 0:
            confirmations.append("12-1 momentum is negative")
        if macd < macd_signal:
            confirmations.append("MACD is below its signal")
        if rsi < 40:
            confirmations.append("RSI is below 40")
        if breakout_down:
            confirmations.append("price broke its prior 63-day low")
        if len(confirmations) >= 2:
            action = TechnicalTimingAction.FAVOR_EXIT
            reasons.extend(confirmations)
            strength = min(-0.35, score)
        else:
            action = TechnicalTimingAction.TIGHTEN_RISK
            reasons.append("bearish regime lacks enough confirmation for an exit signal")
            strength = min(-0.15, score)
    elif score < -0.20:
        action = TechnicalTimingAction.TIGHTEN_RISK
        reasons.append("neutral trend has materially negative momentum confirmation")
        strength = score
    else:
        action = TechnicalTimingAction.WAIT
        reasons.append("trend is inside the neutral band and has no robust trigger")
        strength = score

    return TechnicalTimingSignal(
        action=action,
        strength=_clamp(strength),
        confidence=max(0.0, min(confidence * (0.75 + 0.25 * abs(strength)), 1.0)),
        observed_at=snapshot.bars[-1].provenance.available_at,
        valid_for_bars=parameters.timing_valid_bars,
        execute_on_next_bar=True,
        reasons=tuple(reasons),
        invalidation_conditions=(
            f"Recalculate after {parameters.timing_valid_bars} daily bars or a new corporate action",
            "Trend regime or timing trigger changes before execution",
            "Fundamental thesis, portfolio constraint or risk veto overrides timing",
        ),
    )


def _technical_risks(
    bar_count: int,
    annual_volatility: float,
    max_drawdown: float,
    current_drawdown: float,
    normalized_atr: float,
    volume_ratio: float | None,
    stale_days: int,
) -> tuple[str, ...]:
    risks = []
    if bar_count < 504:
        risks.append("Less than two years of daily history reduces regime confidence")
    if annual_volatility > 0.40:
        risks.append("63-day annualized volatility is above 40%")
    if max_drawdown > 0.25:
        risks.append("252-day maximum drawdown is above 25%")
    if current_drawdown > 0.15:
        risks.append("Current drawdown from the 252-day peak is above 15%")
    if normalized_atr > 0.05:
        risks.append("14-day normalized ATR is above 5%")
    if volume_ratio is None:
        risks.append("Volume confirmation is unavailable")
    if stale_days > 7:
        risks.append("Latest daily bar is stale by more than seven calendar days")
    return tuple(risks)


def _rsi_series(closes: tuple[float, ...], period: int) -> tuple[float | None, ...]:
    if len(closes) <= period:
        raise ValueError("RSI requires more observations than its period")
    changes = tuple(current - previous for previous, current in pairwise(closes))
    average_gain = mean(max(change, 0.0) for change in changes[:period])
    average_loss = mean(max(-change, 0.0) for change in changes[:period])
    result: list[float | None] = [None] * len(closes)
    result[period] = _rsi_from_averages(average_gain, average_loss)
    for index in range(period, len(changes)):
        change = changes[index]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        result[index + 1] = _rsi_from_averages(average_gain, average_loss)
    return tuple(result)


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _macd(
    closes: tuple[float, ...],
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> tuple[float, float, float, float]:
    fast = _ema_series(closes, fast_period)
    slow = _ema_series(closes, slow_period)
    macd_values = tuple(
        _required_value(fast[index], "fast EMA") - _required_value(slow[index], "slow EMA")
        for index in range(slow_period - 1, len(closes))
    )
    signal = _ema_series(macd_values, signal_period)
    histogram = tuple(
        macd_values[index] - _required_value(signal[index], "MACD signal")
        for index in range(signal_period - 1, len(macd_values))
    )
    return (
        macd_values[-1],
        _required_value(signal[-1], "MACD signal"),
        histogram[-1],
        histogram[-2],
    )


def _ema_series(values: tuple[float, ...], period: int) -> tuple[float | None, ...]:
    if len(values) < period:
        raise ValueError("EMA requires at least period observations")
    alpha = 2.0 / (period + 1)
    result: list[float | None] = [None] * len(values)
    result[period - 1] = mean(values[:period])
    for index in range(period, len(values)):
        previous = _required_value(result[index - 1], "previous EMA")
        result[index] = alpha * values[index] + (1 - alpha) * previous
    return tuple(result)


def _normalized_atr(snapshot: AssetDataSnapshot, period: int) -> float:
    adjusted = []
    for bar in snapshot.bars:
        factor = bar.adjusted_close / bar.close
        adjusted.append((bar.high * factor, bar.low * factor, bar.adjusted_close))
    true_ranges = []
    for previous, current in pairwise(adjusted):
        high, low, _ = current
        previous_close = previous[2]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    if len(true_ranges) < period:
        raise ValueError("ATR requires at least period true ranges")
    atr = mean(true_ranges[:period])
    for value in true_ranges[period:]:
        atr = (atr * (period - 1) + value) / period
    return atr / adjusted[-1][2]


def _volume_ratio(snapshot: AssetDataSnapshot, period: int) -> float | None:
    baseline = mean(float(bar.volume) for bar in snapshot.bars[-period - 1 : -1])
    latest = float(snapshot.bars[-1].volume)
    if baseline <= 0 or latest <= 0:
        return None
    return latest / baseline


def _drawdowns(closes: tuple[float, ...]) -> tuple[float, float]:
    peak = closes[0]
    maximum = 0.0
    current = 0.0
    for close in closes:
        peak = max(peak, close)
        current = (peak - close) / peak
        maximum = max(maximum, current)
    return maximum, current


def _required_value(value: float | None, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is unavailable after indicator warm-up")
    return value


def _sign(value: float) -> float:
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


def _clamp(value: float) -> float:
    return max(-1.0, min(float(value), 1.0))
