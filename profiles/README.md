# Investor profiles

Personal financial inputs belong in `profiles/*.local.json`. Git ignores those
files because they can contain income, expenses, net worth and tax residency.

The profile agent accepts either `InvestorProfileRequest` or a JSON object via
`InvestorProfileAgent.create_from_file`. Risk is assessed across three separate
dimensions:

- capacity: financial ability to absorb losses;
- willingness: stated drawdown tolerance;
- need: risk implied by objectives and horizon.

The effective category is the most conservative of the three. Emergency cash
is calculated before investable assets, while asset-level and portfolio-level
volatility and drawdown limits remain separate.

Tax metadata is descriptive and dated. It can make later agents require a tax
review, preserve cost-basis records or limit jurisdictional exposure, but it
must not present itself as a definitive tax calculation.
