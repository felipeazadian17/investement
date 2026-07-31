---
name: technical-analysis
description: Audit or modify the project's daily technical model, tactical entry/exit timing signals, and causal validation. Use for indicator parameters, trend and momentum logic, signal calibration, backtests, or technical-agent reviews.
---

# Technical Analysis

## Contract

Treat technical analysis as a supporting market-state signal. Never let it
override a risk veto, portfolio constraint, or fundamental thesis by itself.
Keep the continuous technical score separate from the tactical timing action.
Its strategic committee weight is zero. Review timing weekly or after a material
event; do not require continuous monitoring.

Before changing parameters or behavior, read
[`../../investigacion/auditoria_modelo_tecnico.md`](../../investigacion/auditoria_modelo_tecnico.md).
Document new evidence there and update this skill when the accepted baseline
changes.

## Baseline

Use complete daily bars and require at least 253 observations; prefer 504.

| Family | Default |
| --- | --- |
| Trend | SMA 50/200 with a 1% neutral band |
| Momentum | 252-to-21-day return plus 63-day return |
| RSI | Wilder 14, interpreted inside the trend regime |
| MACD | EMA 12/26 with 9-period signal |
| Range risk | Wilder ATR 14 divided by adjusted close |
| Volume | latest divided by the prior 20-bar mean |
| Breakout | prior 63-bar high or low |
| Volatility | latest 63 returns, annualized by 252 |
| Drawdown | latest 252 adjusted closes |
| Signal validity | 5 bars, recalculated sooner on new information |

Do not call these parameters universally optimal. They are a stable prior chosen
from published conventions and literature. Promote alternatives only after
robust out-of-sample evidence.

## Causality And Data

1. Sort bars strictly ascending and reject duplicates.
2. Use adjusted OHLC consistently for return and range indicators; use raw close
   only for an executable quoted price.
3. Use only observations whose `available_at` is at or before `as_of`.
4. Compute a signal after bar `t` is available and make the first possible
   execution bar `t+1`.
5. Compare current volume with prior bars; do not include current volume in its
   own baseline.
6. Compute breakouts against prior highs/lows; do not include the current close
   in the threshold.
7. Lower confidence when volume is absent, data is stale, or history is short.

## Timing Logic

Favor entry only in a bullish regime when long and medium momentum are positive
and one fresh trigger exists: volume-confirmed 63-day breakout, RSI pullback
recovery with improving MACD histogram, or confirmed 50/200 cross. Wait when RSI
is above 80 rather than automatically selling.

Favor exit only in a bearish regime with at least two confirmations among
negative 12-1 momentum, MACD below signal, RSI below 40, and a prior-63-day-low
break. Use `tighten_risk` for partial deterioration and `hold` or `wait` when no
fresh trigger exists. In a long-only portfolio, exit means reduce or close; it
never means open a short.

Always return reasons, confidence, observation time, validity, next-bar execution
and invalidation conditions. The timing action is advisory, not an order.

## Validation Gate

Require point-in-time data and a historical universe without survivorship bias.
Use walk-forward testing with frozen parameters, an embargo where overlap exists,
realistic commissions, spread, slippage and taxes. Compare against buy-and-hold
and the same investment process without timing.

Report forward 5/21/63-day rank IC, hit rate, calibration, turnover, net return,
drawdown, and results by sector, capitalization, volatility and market regime.
Test neighborhoods around defaults rather than selecting the single best cell.
Apply a data-snooping correction when many variants are tried. Paper trade before
operational use.

Reject a change that improves only in-sample total return or depends on same-bar
execution, unadjusted corporate actions, unavailable data, or one isolated asset.

The 2024 pilot produced positive one-month directional performance but near-zero
cross-sectional IC. Treat this as regime information, not evidence that technical
scores should select stocks or regain strategic committee weight.
