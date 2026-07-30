---
name: financial-statement
description: Analyze and reconcile income statements, balance sheets, cash-flow statements, LTM periods, earnings quality, invested capital, DuPont drivers, accounting differences, and reporting red flags. Use for fundamental analysis, financial-statement normalization, cash conversion, ROIC, or valuation inputs.
---

# Financial Statement Analysis

## Analysis Contract

Set the purpose, accounting basis, currency and `as_of` before calculating. Use
filings available at the cutoff and preserve reported values separately from
normalizations. Compare a company with its own history and genuinely comparable
peers; avoid universal healthy ranges across industries.

For SEC filings, read [`../edgar-sec-filings/SKILL.md`](../edgar-sec-filings/SKILL.md).

## Three-Statement Reconciliation

Required identities and roll-forwards:

```text
assets = liabilities + equity
ending cash = beginning cash + CFO + CFI + CFF + FX/other effects
ending retained earnings = beginning retained earnings + net income - dividends +/- adjustments
ending debt = beginning debt + issuance - repayment +/- noncash changes
```

Investigate differences rather than forcing plugs. Check units, signs, fiscal
periods, acquisitions, discontinued operations and changes in consolidation.

## LTM and Interim Periods

Distinguish duration and instant facts. For a latest interim filing:

```text
LTM duration metric = latest FY + current YTD - comparable prior YTD
```

Use the latest balance sheet for instant metrics. Reconstruct weighted diluted
shares with share-days. Compare growth YTD/YTD or FY/FY, not sequential rolling
LTM values. All component filings must have been accepted by `as_of`.

## Income Statement

Analyze:

- Revenue by product, segment, geography, volume and price.
- Gross and operating margin, including mix and operating leverage.
- Recurring versus restructuring, impairment, disposal and litigation items.
- R&D and other capitalization policies.
- Interest classification, tax normalization and NCI attribution.
- Diluted EPS and potential dilution from SBC, options and convertibles.

Normalize only when the adjustment is economically justified and separately
visible. Repeated restructuring is not automatically non-recurring.

## Balance Sheet and Invested Capital

Separate operating assets from financing and nonoperating assets:

```text
invested capital = operating assets - non-interest-bearing operating liabilities
```

An equity-side approximation may use common equity plus debt and capitalized
leases, less excess cash and nonoperating investments, with explicit treatment
of preferred stock and NCI.

Inspect:

- Restricted versus available cash.
- Short- and long-term investments.
- Debt maturities, leases, covenants and refinancing risk.
- Receivables, inventory, contract balances and supplier financing.
- Goodwill, acquired intangibles and impairment assumptions.
- Pension deficits, environmental liabilities and contingent claims.

Do not call all cash excess or all investments nonoperating without reviewing
business requirements and regulatory constraints.

## Cash Flow and Earnings Quality

Core reconciliation:

```text
CFO = net income + noncash items - increase in operating working capital
levered FCF = CFO - capex
FCFF cash-flow bridge = CFO - capex + interest * (1 - normalized tax rate)
```

Under US GAAP, interest paid is normally in CFO, so `CFO - capex` is not a clean
FCFF measure. Under IFRS, interest and dividends can be classified differently;
normalize before cross-company comparison.

Analyze CFO versus net income over multiple periods, but do not use one fixed
conversion threshold for every industry. Explain working capital, taxes,
provisions, SBC, leases and acquisition effects.

SBC is noncash in CFO but economically dilutive. Report cash conversion both
before and after the chosen treatment, and model share dilution separately.

## Returns and DuPont

```text
ROE = net margin * asset turnover * financial leverage
ROIC = NOPAT / average invested capital
economic spread = ROIC - WACC
```

Use average beginning/ending balance-sheet denominators where possible. Adjust
EBIT and invested capital consistently for capitalized leases. Compare ROIC to
the cost of capital as an output; never choose WACC merely to preserve a desired
spread.

Five-step DuPont can separate tax burden, interest burden, operating margin,
asset turnover and leverage. For banks and insurers, use sector-specific return,
capital and asset-quality frameworks instead of industrial-company DuPont alone.

## Reporting-Quality Red Flags

- Receivables or contract assets consistently outgrow comparable revenue.
- Inventory growth is inconsistent with demand, capacity or write-down policy.
- Positive earnings coexist with persistently weak CFO without an explained
  growth-working-capital mechanism.
- Supplier finance or factoring changes cash-flow classification.
- Repeated one-off adjustments dominate reported earnings.
- Capitalized costs, useful lives or reserves differ materially from peers.
- Acquisitions obscure organic growth or recurring impairment.
- Auditor changes, control weaknesses, restatements or going-concern language.
- Related-party balances or transactions are material and opaque.
- Buybacks offset SBC in dollars but not in diluted-share economics.

Red flags are investigation prompts, not fraud probabilities. Do not convert a
count of flags into a statistical fraud likelihood without a validated model.

## Accounting Comparability

Identify US GAAP, IFRS or another framework. Review differences in leases,
development costs, inventory methods, impairment reversals, interest/dividend
cash-flow classification, revaluation, pensions and consolidation. Preserve both
reported and normalized views.

When financial-statement data feeds automated peer selection, expose reported
periods and source availability alongside the normalized metrics. Build growth
from comparable LTM or FY periods, use average balance-sheet denominators for
ROE/ROIC where available, normalize capex as an outflow, and keep market cap and
enterprise value bridges internally consistent. Missing segment, gross-margin,
working-capital or accounting-policy data must lower peer feature coverage rather
than being imputed as economically similar.

## Output

1. Cutoff date, source filings, accounting basis, currency and units.
2. Reconciled LTM income, balance-sheet and cash-flow summary.
3. Revenue, margin, working-capital and capital-allocation drivers.
4. Earnings-quality and cash-conversion analysis.
5. ROIC, ROE/DuPont and leverage analysis.
6. Normalizations with reported-to-adjusted bridges.
7. Red flags, missing data and questions requiring note-level review.
8. Valuation implications without turning accounting ratios directly into a
   buy/sell recommendation.
