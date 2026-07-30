---
name: valuation-model
description: Select, build, audit, and triangulate corporate valuation models, including FCFF/FCFE DCF, DDM, residual income, SOTP, asset-based valuation, and market multiples. Use when model applicability, intrinsic value, relative valuation, financial institutions, startups, cyclicals, or valuation traps matter.
---

# Valuation Model Selection and Triangulation

## Start With the Economic Claim

Choose the cash flow, discount rate and value claim together:

| Claim valued | Cash flow or income | Discount rate | Initial output |
| --- | --- | --- | --- |
| Operating enterprise | FCFF | WACC | Enterprise value |
| Common equity | FCFE | Cost of equity | Common equity value |
| Dividend claim | Dividends | Cost of equity | Common equity value |
| Residual income | Net income less equity charge | Cost of equity | Common equity value |

Do not mix columns. In particular, `CFO - capex` under US GAAP is generally a
levered cash flow and cannot be discounted at WACC without an interest bridge.

## Selection Framework

```text
Is the company a financial institution?
|-- Yes: residual income, DDM and justified P/B; avoid FCFF/WACC.
|-- No:
    |-- Positive, interpretable operating profit and invested capital?
    |   |-- Yes: FCFF DCF plus EV-based comparables.
    |   `-- No: life-cycle or distress scenarios; consider residual income,
    |           asset value, EV/revenue or option-style analysis.
    |-- Multiple economically different segments? Use SOTP.
    |-- Highly cyclical? Normalize at mid-cycle before DCF or multiples.
```

Use the simplest model that represents the business and available data. More
detail does not compensate for weak inputs.

## FCFF DCF

Read [`../dcf/SKILL.md`](../dcf/SKILL.md) for the full procedure. Core identities:

```text
FCFF = NOPAT + D&A - capex - change in operating working capital
EV = PV(explicit FCFF) + PV(terminal value)
common equity = EV + nonoperating assets - non-common claims
```

Use point-in-time LTM data, market-backed WACC, driver-based convergence,
terminal reinvestment tied to `g / stable ROIC`, a complete equity bridge and a
5x5 WACC/`g` sensitivity matrix.

## DDM

Use when dividends have an observable and sustainable relationship to earnings
and capital requirements.

```text
P0 = sum(D_t / (1+Ke)^t) + terminal dividend value
terminal value = D_(n+1) / (Ke-g)
```

For banks and insurers, forecast regulatory capital, ROE, payout capacity and
growth together. A stable dividend history alone is not enough if capital ratios
or loss reserves are changing.

## Residual Income

Useful when free cash flow is negative or difficult to define but book value and
earnings are meaningful, especially for financial institutions.

```text
RI_t = net income_t - Ke * beginning common book value_t
equity value = current common book value + PV(future RI)
```

Normalize accounting distortions and enforce clean-surplus consistency between
beginning book value, earnings, dividends, OCI and ending book value.

## SOTP

Value each segment with the method appropriate to its economics. Add corporate
assets and subtract corporate claims once. Apply a holding-company discount only
when supported by taxes, leakage, governance or structural costs; do not use it
as a balancing plug.

## Relative Valuation

Match numerator and denominator:

| Multiple | Claim | Appropriate denominator |
| --- | --- | --- |
| P/E, P/B, P/FCFE | Equity | Net income, common book value, FCFE |
| EV/EBITDA, EV/EBIT, EV/Sales | Enterprise | Pre-financing operating metric |

Select peers by business mix, geography, life-cycle, margins, growth, capital
intensity, accounting and leverage. Use robust medians and disclose exclusions.
Do not blend incompatible values merely because both are available.

### Automated Peer Selection

Treat industry classifications as candidate generators, not final peer sets. Use
this deterministic sequence:

1. Fix the valuation cutoff and candidate universe revision.
2. Reject the target itself, unavailable-at-cutoff profiles, incompatible company
   types, incompatible life-cycle stages and unrelated sectors/business mixes.
3. Score business activity and segment revenue mix before numerical features.
4. Score growth, profitability/returns, capital intensity, log-scaled size and
   leverage/risk using robust median/MAD scaling across the candidate universe.
5. Change family weights by multiple. P/E needs more leverage/risk matching;
   P/FCF and EV/EBIT need more capital-intensity matching; EV/Sales needs more
   growth, gross-margin and unit-economics matching.
6. Require explicit similarity and feature-coverage thresholds. Prefer 5-12 peers
   and fail when the minimum group cannot be supported.
7. Preserve selected, eligible-not-selected and rejected candidates with scores,
   coverage, reasons and source dates.
8. Only after selection, calculate multiples, apply robust outlier controls and
   report dispersion.

Never use the valuation multiple itself as a peer-selection feature. That makes
the selection circular and can manufacture the desired conclusion. Investor
style preferences also belong after objective peer selection.

For every candidate, build point-in-time features from comparable accounting
periods. Use segment mix, business model, geography, accounting standard,
life-cycle, revenue/EBIT/FCF growth, margins, ROIC/ROE, cash conversion,
capex/revenue, asset turnover, market cap, enterprise value, assets, net
debt/EBITDA, coverage, beta, volatility, cyclicality and SBC/revenue when
available. Missing variables reduce feature coverage; they do not receive a
neutral or perfect similarity score.

Keep the valued claim consistent:

```text
P/E, P/B, P/FCF result = common equity value
EV/EBITDA, EV/EBIT, EV/Sales result = enterprise value
common equity value = enterprise value + nonoperating assets - non-common claims
```

An EV multiple cannot be blended with equity value per share until the target's
EV-to-equity bridge has been applied per share.

Use justified multiples as a reasonableness check:

```text
justified P/B = (ROE - g) / (Ke - g)
```

## Special Cases

### Early-Stage Companies

Do not cap observed growth and extrapolate a single path. Build probability-
weighted scenarios for survival, addressable market, revenue, target margin,
sales-to-capital or ROIC, funding needs and dilution. Cross-check EV/revenue only
against peers at comparable stages.

### Cyclicals

Use normalized revenue, margins, working capital and reinvestment across a full
cycle. Peak earnings often produce deceptively low P/E values.

### Distressed Companies

Separate going-concern, restructuring and liquidation outcomes. Reflect debt
priority, dilution, covenant constraints and probability of default.

## Valuation-Trap Checks

- Cash flow and discount rate are inconsistent.
- Current earnings are cyclical peak or contain one-off gains.
- Revenue growth is purchased through uneconomic reinvestment.
- ROIC is measured on incomplete invested capital.
- SBC is added back without modeling dilution.
- Leases are debt in the bridge but operating in EBIT, or vice versa.
- Cash, investments, debt or minority interest are double counted.
- A historical filing has been reconstructed using data unavailable at `as_of`.
- Terminal `g` exceeds WACC, risk-free rate or stable ROIC.
- Comparable companies differ materially in stage or economics.

## Triangulation

Use at least one intrinsic and one market-based approach when applicable, but do
not average mechanically. Explain why methods differ and which assumptions drive
the range. Reverse DCF can reveal what growth, margins or ROIC the market price
already implies.

## Output

1. Model selected and models rejected, with reasons.
2. Cutoff date, currency, sources and point-in-time limitations.
3. Base, downside and upside values with assumptions.
4. Sensitivity or probability-weighted scenario range.
5. Cross-checks and implied market expectations.
6. Valuation traps, missing data and invalidation conditions.

Valuation is an analytical estimate, not a trading signal by itself.
