# Sector Cost-of-Capital Fallbacks

Sector ranges are diagnostic fallbacks. They must not replace a dated company
beta, market ERP, risk-free rate, issuer credit spread and market-value capital
structure when those inputs are available.

## Fallback Order

1. Company beta from at least 24 aligned monthly observations.
2. Bottom-up unlevered sector beta, relevered to the issuer's target market debt
   ratio.
3. Broad sector WACC range only when neither beta path is available.

For debt, prefer traded bond/CDS yields, then a dated synthetic spread based on
interest coverage. Do not add arbitrary small-cap or qualitative premiums on top
of an already levered beta without explaining the possible double count.

## Diagnostic Ranges

These ranges are broad and must be refreshed for the market date and currency:

| Sector | Illustrative WACC | Main reason for dispersion |
| --- | --- | --- |
| Communication Services | 7-11% | Stable telecom versus growth media |
| Consumer Discretionary | 8-12% | Cyclicality and operating leverage |
| Consumer Staples | 6-9% | Defensive demand and brand durability |
| Energy | 8-13% | Commodity beta, country and reserve risk |
| Health Care | 7-12% | Pipeline, patent and regulatory risk |
| Industrials | 7-11% | Cycle, contracts and capital intensity |
| Information Technology | 7-13% | Life-cycle and concentration differences |
| Materials | 8-12% | Commodity and capacity cycle |
| Real Estate | 6-11% | Leverage, rates and property mix |
| Utilities | 5-9% | Regulation, leverage and duration |

Do not apply FCFF/WACC DCF to banks, insurers or brokers merely because a
financial-sector range exists. Use cost of equity with residual income, DDM or
justified P/B.

## Checks

- Compare calculated company WACC with bottom-up sector cost of capital.
- Explain deviations through beta, leverage, credit spread, country exposure or
  currency, not through an unexplained plug.
- ROIC above WACC is an output about value creation, not a rule requiring WACC
  to sit two to four points below ROIC.
