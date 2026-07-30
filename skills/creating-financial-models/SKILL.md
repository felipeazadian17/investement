---
name: creating-financial-models
description: Build auditable point-in-time financial models with explicit inputs, calculations, outputs, scenarios, sensitivities, and validation. Use for DCF, three-statement models, Monte Carlo analysis, project finance, M&A, LBO, or decision models where assumption provenance and model integrity matter.
---

# Auditable Financial Modeling

## Architecture

Separate the model into four layers:

1. **Observed inputs**: dated filings, market data and operating facts.
2. **Assumptions**: explicit forecasts, scenarios and policy choices.
3. **Calculations**: formulas with no hidden plugs.
4. **Outputs**: valuation, sensitivities, checks and decision metrics.

Every input must carry unit, currency, period, `available_at`, source and any
normalization. Never mix observed history with assumptions in the same field.

## Point-in-Time Gate

Before calculating:

- Set `as_of` and reject any later filing acceptance or market observation.
- Distinguish duration facts from instant facts.
- Reconcile annual and interim periods before building LTM.
- Keep original reported values and record every adjustment separately.
- Reject silent fallback values. A default is allowed only as a named scenario
  assumption with a source and sensitivity range.

## DCF Models

For corporate valuation, follow [`../dcf/SKILL.md`](../dcf/SKILL.md). Required
features include FCFF/WACC consistency, market-value capital weights, operating
driver convergence, terminal reinvestment, a complete EV-to-equity bridge and
invalid-cell handling in sensitivity tables.

Use [`dcf_model.py`](dcf_model.py) only as a calculation reference. Production
analysis in this repository must call `investement.valuation` so formulas do not
diverge from the tested agent.

## Three-Statement Forecasting

Forecast the income statement, balance sheet and cash-flow statement as one
system:

- Revenue by operating driver where available.
- Costs coherently with revenue, capacity and inflation.
- Working capital through operating efficiency ratios.
- Maintenance and growth capex separately when disclosures permit.
- Debt, interest, cash and financing needs through a transparent circularity
  solver or an explicit iteration.
- Share count through buybacks, issuance, options and convertibles.

Required checks:

```text
assets = liabilities + equity
beginning cash + cash flow change = ending cash
retained earnings roll-forward reconciles
debt roll-forward reconciles with interest and financing cash flow
```

## Scenarios

Use scenarios when the business has non-linear outcomes, limited history or
material strategic uncertainty. Each scenario must vary coherent groups of
drivers, not isolated numbers.

Typical scenario dimensions:

- Revenue growth and market share.
- Margin path and operating leverage.
- Reinvestment, working capital and capital intensity.
- Cost of capital and credit spread.
- Survival, refinancing, regulation or product approval.
- Dilution and capital raising.

Probabilities must sum to one and be disclosed. Do not interpret an expected
value as the most likely realized value.

## Sensitivity

Use sensitivity for continuous uncertainty and scenarios for structural states.

- DCF default: 5x5 WACC versus terminal `g`.
- Mark economically invalid cells as `N/A`.
- Add one-way or tornado analysis for margins, growth, ROIC, capex, working
  capital and dilution when material.
- Restore the base model after each test; avoid state leakage between cells.
- Show both absolute output and change versus base.

The generic helper [`sensitivity_analysis.py`](sensitivity_analysis.py) can be
used for non-DCF models, but callers remain responsible for economic validators
and state restoration.

## Monte Carlo

Use Monte Carlo only when distributions and dependencies are defensible.

- Specify distribution choice and calibration source.
- Model correlations; independent draws are not a neutral assumption.
- Reject impossible draws before valuation.
- Use enough iterations for stable percentiles and report the random seed.
- Report median, mean, percentiles and probability of loss, not only a chart.

Monte Carlo does not repair a structurally wrong model.

## Model-Specific Requirements

| Model | Additional requirements |
| --- | --- |
| M&A | Standalone values, synergies, timing, financing, fees, accretion/dilution |
| LBO | Sources/uses, debt tranches, mandatory amortization, cash sweep, exit range |
| Project finance | Construction schedule, availability, covenants, DSCR/LLCR, reserves |
| Real estate | Lease roll, occupancy, tenant improvements, cap rates, debt maturity |
| Turnaround | Liquidity runway, restructuring costs, survival and financing dilution |

## Validation

1. Reconcile all statements and roll-forwards.
2. Verify units, signs, currency and timing conventions.
3. Test formula monotonicity where economics imply it.
4. Check terminal-value share and implied multiples.
5. Compare with historical performance and relevant peers without forcing a fit.
6. Inspect extreme but valid inputs rather than clipping them silently.
7. Run downside liquidity and covenant checks.
8. Preserve an audit trail of inputs, assumptions and model version.

## Output

Provide an assumptions table, calculation summary, scenario/sensitivity results,
validation checks, material limitations and exact files or code used. State which
results are observed, modeled and judgmental.
