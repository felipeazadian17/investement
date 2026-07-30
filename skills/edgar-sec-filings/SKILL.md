---
name: edgar-sec-filings
description: Retrieve and analyze SEC EDGAR filings point-in-time, including as-filed XBRL from 10-K/10-Q, material 8-K events, proxy governance, Form 4 insider activity, narrative changes, provenance, and LTM reconstruction. Use for SEC filing extraction, fundamental history, filing quality, risks, or event analysis.
---

# Point-in-Time SEC Filing Analysis

## Source Policy

Use official SEC filings or an EDGAR client that preserves the as-filed document.
Do not present Yahoo or another aggregator as equivalent to the filing. Secondary
sources may be reconciliation checks, never the authoritative XBRL history.

Set an SEC identity containing a real name and contact email. Respect current SEC
fair-access guidance, cache responses and avoid burst requests.

## Filing Types

| Filing | Primary use |
| --- | --- |
| 10-K | Audited annual statements, notes, MD&A and risk factors |
| 10-Q | Interim YTD statements, notes and trend changes |
| 8-K | Material events, earnings releases, restatements, M&A and management changes |
| DEF 14A | Governance, compensation, dilution and related-party matters |
| Form 4 | Insider transactions and transaction coding |
| 13D/G | Significant ownership and activist intent |
| 13F | Lagged institutional holdings; never current positioning |

## Point-in-Time Gate

For every observation record:

- Filing form, fiscal period and accession number.
- Filing date and acceptance timestamp.
- `available_at` equal to the acceptance timestamp or later.
- Retrieval timestamp and raw filing URL.
- XBRL concept selected, unit, period and adjustments.

Reject filings accepted after analysis `as_of`. Exclude amendments by default to
avoid duplicate periods; include an amendment only through an explicit
restatement policy. Do not use a later Company Facts value to rewrite what an
earlier market participant could observe.

## As-Filed XBRL Extraction

Prefer consolidated, non-dimensioned facts for the matching statement period.
Distinguish:

- **Duration facts**: revenue, EBIT, net income, pretax income, tax, interest,
  CFO, capex, D&A and stock-based compensation.
- **Instant facts**: cash, investments, debt, leases, preferred stock,
  noncontrolling interest, pension claims, equity, assets and current shares.

Use a documented concept fallback order because issuers can select different
standard concepts. Preserve the chosen concept in provenance. A missing concept
is `None`, not zero.

For current shares, inspect the DEI cover fact
`EntityCommonStockSharesOutstanding` when it is absent from the balance-sheet
presentation. It may have an instant date after period end but before filing
acceptance; that is valid if recorded explicitly.

Treat capex as a positive outflow in the normalized model while preserving the
reported sign in raw provenance.

## Period Selection

For 10-Q cash-flow and income duration facts, select fiscal YTD, not the isolated
quarter, when the downstream model constructs LTM. Determine `period_start` from
facts ending on the report date and reject ambiguous or implausible durations.

For a latest interim period:

```text
LTM metric = preceding FY + current YTD - prior-year comparable YTD
```

Apply this only to additive duration facts. Use the latest interim balance sheet
for instant facts. Reconstruct LTM weighted-average diluted shares with
share-days rather than adding/subtracting share counts as ordinary values.

Request at least eight recent 10-K/10-Q filings. If the preceding FY or comparable
YTD remains unavailable, fail the LTM build instead of substituting current data.

Comparable growth is YTD/YTD or FY/FY. Never call sequential rolling-LTM change
an annual growth rate.

## Cash-Flow Interpretation

Label `CFO - capex` as levered free cash flow or cash conversion under US GAAP.
Interest paid is usually classified in CFO. For FCFF valuation, bridge interest
after tax or build FCFF from NOPAT, reinvestment and working capital.

Stock-based compensation is noncash in CFO but economically dilutive. Analyze
both cash conversion and diluted/current share counts; do not simply subtract or
ignore SBC without modeling its effect.

If leases are capitalized for valuation, collect the liability and reclassify
implied lease interest consistently in EBIT, invested capital, WACC and the
enterprise-to-equity bridge.

## Statement Analysis

### Income Statement

- Revenue by segment/geography and comparable growth.
- Gross and operating margin trajectory.
- Recurring versus one-off items.
- Tax-rate normalization and interest classification.

### Balance Sheet

- Cash and nonoperating investments separately.
- Debt and maturity structure.
- Operating leases, preferred stock, NCI and pension claims.
- Working-capital efficiency and asset-quality indicators.
- Goodwill, acquired intangibles and impairment exposure.

### Cash Flow

- CFO versus net income and accrual quality.
- Maintenance versus growth capex when disclosed.
- Working-capital contribution to cash flow.
- SBC, acquisitions, dividends, buybacks and issuance.

## Narrative and Event Analysis

Compare each filing with the prior comparable form:

- New, removed or intensified risk factors.
- Changes in MD&A explanations, guidance and liquidity language.
- Auditor opinion, controls, restatement or going-concern changes.
- Segment reorganization or accounting-policy changes.
- Debt agreements, covenants and refinancing events.

Prioritize these 8-K events:

| Item/event | Required response |
| --- | --- |
| 4.02 restatement | Invalidate affected historical analysis and rebuild |
| 2.02 earnings release | Reconcile non-GAAP and filed GAAP metrics |
| 1.01 material agreement/M&A | Model consideration, financing and claims |
| 5.02 CEO/CFO change | Assess succession and control risk |
| Bankruptcy/default | Switch to distress and claim-priority analysis |

Avoid keyword-count sentiment as a standalone signal. Use text changes in their
financial and legal context, with short paraphrases and exact section references.

## Insider and Ownership Data

- Distinguish open-market purchases from grants, exercises, gifts and 10b5-1
  sales.
- Measure transaction size relative to the insider's holdings and compensation.
- Treat Form 4 as supporting evidence, not a valuation input.
- State the 13F reporting lag; positions may have changed before publication.

## Quality Checks

1. Statement periods and units match.
2. Consolidated facts were selected over segment dimensions.
3. LTM bridge sources are all available at `as_of`.
4. Cash, debt and investments do not overlap.
5. Current and diluted shares have not been confused.
6. Reported totals reconcile where sufficient facts exist.
7. Restatements and accounting changes are visible.
8. Missing claims remain explicit rather than becoming silent zeros.

## Output

Include filing metadata, source links, extracted statement table, LTM bridge,
quality checks, narrative changes, material events, missing data and investment
implications. Separate facts, calculations and analyst judgment.

For this repository, the implementation is in
`src/investement/data/edgar_provider.py` and the DCF methodology is documented in
[`../../investigacion/auditoria_modelo_dcf.md`](../../investigacion/auditoria_modelo_dcf.md).
