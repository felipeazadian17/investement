---
name: risk-management
description: Audit or modify asset, portfolio, liquidity, concentration, tail-risk, stress-testing, and pre-trade veto logic for the Investement project.
---

# Risk Management

Read `../../investigacion/auditoria_portfolio_riesgo_gobernanza.md` before
changing limits or metrics.

## Contract

Separate hard breaches from warnings. A passed risk check is neutral alpha with
score zero. A hard breach sets `risk_veto=True`; warnings lower confidence or
request review but do not silently become prohibitions.

For assets, validate profile restrictions, proposed weight, recent annualized
volatility, 252-day drawdown and 20-day dollar liquidity. Report current drawdown,
normalized ATR and deteriorating technical timing as diagnostics.

For portfolios, validate weights plus cash, profile volatility and drawdown,
and caps by asset, sector, country, asset class and currency. Report historical
95% VaR and Expected Shortfall, effective number of assets, turnover, risk
contributions and data observations.

Use historical tail metrics as diagnostics, not forecasts. Add historical,
hypothetical and reverse stress tests before derivatives or leverage. Options
require aggregate delta, gamma, vega and liquidity; do not treat premium weight
as the complete risk exposure.

## Validation

Use point-in-time aligned returns, multiple regimes and walk-forward limits.
Backtest breach frequency and false vetoes. Reconcile target and current exposure
with the broker. Never weaken a profile limit because the optimizer cannot find a
feasible portfolio; increase cash or fail loudly.
