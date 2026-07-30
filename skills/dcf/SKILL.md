---
name: dcf-valuation
description: Build or audit point-in-time corporate DCF valuations with LTM financials, FCFF/WACC consistency, market-derived capital costs, driver-based convergence, enterprise-to-equity bridges, terminal-growth validation, and sensitivity analysis. Use for intrinsic value, fair value, price target, DCF, WACC, terminal value, or valuation-model review requests.
---

# Point-in-Time DCF Valuation

## Non-Negotiable Rules

1. Match cash flow and discount rate:
   - FCFF -> WACC -> enterprise value.
   - FCFE -> cost of equity -> common equity value.
2. Do not label `CFO - capex` as FCFF under US GAAP. Interest paid is normally
   in CFO, so this measure is levered. A cash-flow-statement bridge is:
   `FCFF = CFO - capex + interest expense * (1 - marginal tax rate)`.
3. Use only observations available at the valuation `as_of`. Record source,
   period, filing acceptance date, market observation date and adjustments.
4. Never silently replace missing company data with generic defaults.
5. Keep observed extreme values. Control implausible extrapolation through
   convergence and scenarios, not by rewriting history.
6. Do not force FCFF DCF onto financial institutions, early-stage companies,
   negative-EBIT businesses or companies with non-positive invested capital.

## Workflow

Track these steps:

```text
- [ ] Select the applicable valuation model
- [ ] Establish the point-in-time cutoff and data provenance
- [ ] Build LTM financials and comparable growth
- [ ] Reconcile FCFF and invested capital
- [ ] Calculate market-backed WACC
- [ ] Project operating drivers and convergence
- [ ] Validate terminal economics
- [ ] Bridge enterprise value to common equity
- [ ] Run sensitivity and cross-checks
- [ ] Report assumptions, risks and invalidation conditions
```

## 1. Select the Model

Use FCFF DCF for a non-financial operating company when revenue, EBIT, invested
capital and a plausible path to positive FCFF are observable.

Route other cases explicitly:

| Company | Primary approach |
| --- | --- |
| Bank, insurer, broker or other financial institution | Residual income, DDM or justified P/B |
| Stable dividend payer with interpretable payout policy | DDM plus residual income or multiples |
| Early-stage or negative EBIT | Probability-weighted revenue, margin, survival and dilution scenarios |
| Cyclical | Mid-cycle normalized earnings and commodity/capacity scenarios |
| Conglomerate | SOTP with method chosen per segment |
| Distressed | Reorganization/liquidation scenarios; do not use a single Gordon perpetuity |

Fail closed when the required model has not been implemented.

## 2. Build Point-in-Time LTM

Prefer as-filed SEC XBRL from 10-K and 10-Q filings accepted by `as_of`. Request
enough history for the bridge; eight filings is the minimum default, not a
guarantee for every fiscal calendar.

For the latest interim period:

```text
LTM metric = latest FY + current YTD - prior-year comparable YTD
```

Apply the bridge to additive duration facts such as revenue, EBIT, net income,
CFO, capex, taxes, interest, D&A and stock-based compensation. Use the latest
instant facts for balance-sheet values. Reconstruct diluted LTM shares with
share-days; use the greater of current shares and diluted LTM shares when a
fully diluted current count is unavailable.

Initial growth must compare like periods: YTD versus comparable YTD, or FY
versus prior FY. Do not compare two consecutive rolling LTM periods as though
that were annual growth.

## 3. Reconcile FCFF

Preferred operating formula:

```text
NOPAT = adjusted EBIT * (1 - normalized tax rate)
FCFF = NOPAT + D&A - capex - change in operating working capital
```

Cash-flow-statement cross-check:

```text
FCFF = CFO - capex + interest expense * (1 - tax rate)
```

If operating leases are treated as debt, estimate their interest component,
add it back to reported EBIT, include leases in invested capital/WACC and
subtract the lease liability in the equity bridge. Do all four or none.

## 4. Calculate Market-Backed WACC

```text
Ke = risk-free rate + adjusted beta * equity risk premium
Kd = risk-free rate + issuer default spread
WACC = E/(D+E) * Ke + D/(D+E) * Kd * (1-T)
```

Requirements:

- Risk-free rate and ERP must be dated observations available at `as_of`.
- Estimate company beta from five years of aligned monthly total returns versus
  a broad market benchmark, with at least 24 observations. Record raw and
  adjusted beta. Use a sector beta only as a documented fallback.
- Estimate default spread from traded debt/CDS when available. Otherwise use a
  dated synthetic-rating table and issuer interest coverage.
- Use market equity and debt plus capitalized leases for capital weights.
- Treat [sector-wacc.md](sector-wacc.md) as a reasonableness check, not an input
  that overrides observable company and market data.

## 5. Project Drivers and Convergence

Use at least five explicit years; seven is the project default. Project revenue,
EBIT margin, NOPAT, ROIC, reinvestment and FCFF rather than applying one FCF CAGR.

```text
reinvestment rate_t = growth_t / ROIC_t
FCFF_t = NOPAT_t * (1 - reinvestment rate_t)
```

Fade initial growth toward terminal growth. Fade abnormal margins toward a
normalized historical or sector margin. Fade excess ROIC toward a stable return,
normally near WACC absent a defensible durable advantage. A growth rate above
ROIC can legitimately produce negative FCFF because reinvestment exceeds NOPAT.

For startups or unstable businesses, use separate scenarios for survival,
revenue, target margin, capital intensity and dilution. Do not summarize that
uncertainty with one deterministic CAGR.

## 6. Validate Terminal Value

For a perpetual-growth terminal value:

```text
terminal reinvestment = g / stable ROIC
terminal FCFF = terminal NOPAT * (1 - g / stable ROIC)
TV = terminal FCFF / (WACC - g)
```

Require all of the following:

- `0 <= g < WACC`.
- `g <= long-run risk-free rate` for a nominal same-currency model.
- `g < stable ROIC`.
- Currency, inflation and discount-rate assumptions are consistent.

An exit multiple is a cross-check, not a way to hide an invalid perpetuity.

## 7. Bridge Enterprise Value to Common Equity

```text
common equity value = enterprise value
  + cash and equivalents
  + short-term investments
  + nonoperating long-term investments
  - debt
  - operating lease liabilities
  - preferred stock
  - noncontrolling interests
  - unfunded pension claims
  +/- other explicit nonoperating adjustments
```

Never combine `net debt` with a separate cash add-back unless the definition is
explicit; that double counts cash. List unreported bridge items and state when
they are treated as zero.

## 8. Sensitivity and Validation

Produce a 5x5 WACC-versus-`g` matrix by default:

- WACC: base +/-2% in 1% steps.
- `g`: base +/-1% in 0.5% steps.
- Invalid cells where `g >= WACC`, `g > risk-free` or `g >= stable ROIC` are
  `N/A`, never enormous numeric outputs.

Also report terminal-value share, implied EV multiples, valuation versus market
price, observed cash conversion and the effect of the complete equity bridge.
Large deviations are prompts to inspect assumptions, not reasons to force the
DCF toward the current enterprise value.

## Output

Include:

1. Model selection and cutoff date.
2. LTM reconciliation and source filings.
3. FCFF, WACC and bridge formulas with dated inputs.
4. Annual operating projection and terminal reinvestment.
5. Enterprise value, common equity value and value per diluted share.
6. Sensitivity matrix and scenario range.
7. Missing data, model risks and invalidation conditions.

For this repository, read
[`../../investigacion/auditoria_modelo_dcf.md`](../../investigacion/auditoria_modelo_dcf.md)
for the implemented methodology and primary references.
