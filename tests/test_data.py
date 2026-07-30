import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pandas as pd

from investement.data import (
    AlphaVantageProvider,
    CachedMarketDataProvider,
    EdgarProvider,
    JsonPriceBarCache,
    ReconciledMarketDataProvider,
    YFinanceProvider,
    normalize_symbol,
)
from investement.domain import DataProvenance, InstrumentType, PriceBar


class FakeFrame:
    empty = False

    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        return iter(self._rows)


class FakeFiling:
    form = "10-K"
    accession_number = "0001-24-000001"
    primary_document = "report.htm"
    homepage_url = "https://www.sec.gov/Archives/example"

    def __init__(
        self,
        filing_date=date(2024, 2, 1),
        acceptance_datetime=datetime(2024, 2, 1, 20, tzinfo=UTC),
    ):
        self.filing_date = filing_date
        self.acceptance_datetime = acceptance_datetime

    def text(self):
        return "filing body"


class FakeFilings(list):
    def head(self, limit):
        return self[:limit]

    def latest(self):
        return self[0]


class FakeCompany:
    cik = "0000320193"

    def __init__(self, symbol, filings=None):
        self.symbol = symbol
        self.calls = []
        self.filings = filings or [FakeFiling()]

    def get_filings(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFilings(self.filings)


class FakeMarketDataProvider:
    name = "fake-market-data"

    def __init__(self, bars):
        self.bars = bars
        self.calls = 0

    def history(self, symbol, start, end, interval="1d"):
        self.calls += 1
        return self.bars


class DataProviderTests(unittest.TestCase):
    def test_symbol_normalization(self):
        self.assertEqual(normalize_symbol(" aapl.us "), "AAPL")
        self.assertEqual(normalize_symbol("700.hk"), "0700.HK")

    def test_yfinance_is_explicit_about_adjustments_and_normalizes_rows(self):
        captured = {}

        def downloader(**kwargs):
            captured.update(kwargs)
            return FakeFrame(
                [
                    (
                        date(2024, 1, 2),
                        {
                            "Open": 100.0,
                            "High": 103.0,
                            "Low": 99.0,
                            "Close": 102.0,
                            "Adj Close": 101.5,
                            "Volume": 1000,
                        },
                    )
                ]
            )

        provider = YFinanceProvider(
            downloader=downloader,
            clock=lambda: datetime(2024, 1, 3, tzinfo=UTC),
        )
        bars = provider.history("aapl.us", date(2024, 1, 1), date(2024, 1, 3))
        self.assertFalse(captured["auto_adjust"])
        self.assertTrue(captured["actions"])
        self.assertEqual(captured["tickers"], "AAPL")
        self.assertEqual(captured["end"], "2024-01-04")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].adjusted_close, 102.0)
        self.assertEqual(bars[0].provenance.metadata["yahoo_adjusted_close_ignored"], 101.5)
        self.assertIsNotNone(bars[0].timestamp.tzinfo)
        self.assertLessEqual(bars[0].provenance.available_at, bars[0].provenance.retrieved_at)

    def test_yfinance_builds_causal_total_return_without_applying_split_twice(self):
        provider = YFinanceProvider(
            downloader=lambda **kwargs: FakeFrame(
                [
                    (
                        date(2024, 1, 2),
                        {
                            "Open": 99.0,
                            "High": 101.0,
                            "Low": 98.0,
                            "Close": 100.0,
                            "Adj Close": 90.0,
                            "Volume": 1000,
                            "Dividends": 0.0,
                            "Stock Splits": 0.0,
                        },
                    ),
                    (
                        date(2024, 1, 3),
                        {
                            "Open": 98.0,
                            "High": 100.0,
                            "Low": 97.0,
                            "Close": 99.0,
                            "Adj Close": 91.0,
                            "Volume": 1200,
                            "Dividends": 2.0,
                            "Stock Splits": 0.0,
                        },
                    ),
                    (
                        date(2024, 1, 4),
                        {
                            "Open": 100.0,
                            "High": 102.0,
                            "Low": 99.0,
                            "Close": 101.0,
                            "Adj Close": 92.0,
                            "Volume": 1300,
                            "Dividends": 0.0,
                            "Stock Splits": 2.0,
                        },
                    ),
                ]
            ),
            clock=lambda: datetime(2024, 1, 6, tzinfo=UTC),
        )
        bars = provider.history("AAPL", date(2024, 1, 1), date(2024, 1, 5))
        self.assertAlmostEqual(bars[1].adjusted_close, 101.0)
        self.assertAlmostEqual(bars[2].adjusted_close, 101.0 * 101.0 / 99.0)
        self.assertEqual(bars[2].provenance.metadata["stock_split"], 2.0)

    def test_yfinance_excludes_an_unfinished_daily_bar(self):
        provider = YFinanceProvider(
            downloader=lambda **kwargs: FakeFrame(
                [
                    (
                        date(2024, 1, 2),
                        {
                            "Open": 100.0,
                            "High": 103.0,
                            "Low": 99.0,
                            "Close": 102.0,
                            "Adj Close": 101.5,
                            "Volume": 1000,
                        },
                    )
                ]
            ),
            clock=lambda: datetime(2024, 1, 2, 20, tzinfo=UTC),
        )
        bars = provider.history("AAPL", date(2024, 1, 1), date(2024, 1, 2))
        self.assertEqual(bars, [])

    def test_edgar_sets_identity_and_preserves_filing_availability(self):
        identities = []
        companies = []

        def factory(symbol):
            company = FakeCompany(symbol)
            companies.append(company)
            return company

        provider = EdgarProvider(
            identity="Investement Research research@example.com",
            company_factory=factory,
            identity_setter=identities.append,
            clock=lambda: datetime(2024, 2, 2, tzinfo=UTC),
        )
        records = provider.latest_filings("aapl", forms=("10-k",), limit=1)
        self.assertEqual(identities, ["Investement Research research@example.com"])
        self.assertEqual(companies[0].calls[0]["form"], ["10-K"])
        self.assertFalse(companies[0].calls[0]["amendments"])
        self.assertEqual(records[0].filing_date, date(2024, 2, 1))
        self.assertEqual(records[0].accepted_at, datetime(2024, 2, 1, 20, tzinfo=UTC))
        self.assertEqual(records[0].provenance.source, "sec-edgar")

    def test_edgar_filters_by_acceptance_before_applying_limit(self):
        future = FakeFiling(
            filing_date=date(2024, 2, 1),
            acceptance_datetime=datetime(2024, 2, 1, 22, tzinfo=UTC),
        )
        past = FakeFiling(
            filing_date=date(2024, 1, 31),
            acceptance_datetime=datetime(2024, 1, 31, 22, tzinfo=UTC),
        )
        provider = EdgarProvider(
            identity="Investement Research research@example.com",
            company_factory=lambda symbol: FakeCompany(symbol, [future, past]),
            clock=lambda: datetime(2024, 2, 2, tzinfo=UTC),
        )
        records = provider.latest_filings(
            "AAPL",
            limit=1,
            available_before=datetime(2024, 2, 1, 21, tzinfo=UTC),
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].filing_date, date(2024, 1, 31))

    def test_edgar_requires_contact_identity(self):
        with self.assertRaises(ValueError):
            EdgarProvider(identity="anonymous")

    def test_edgar_extracts_consolidated_xbrl_from_the_as_filed_statement(self):
        report_end = date(2024, 3, 30)
        period_column = "2024-03-30 (YTD)"
        income = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
                    "dimension_label": "Products",
                    period_column: 80.0,
                },
                {
                    "concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
                    "dimension_label": None,
                    period_column: 200.0,
                },
                {
                    "concept": "us-gaap_OperatingIncomeLoss",
                    "dimension_label": None,
                    period_column: 40.0,
                },
                {
                    "concept": "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
                    "dimension_label": None,
                    period_column: 10.0,
                },
                {
                    "concept": "us-gaap_NetIncomeLoss",
                    "dimension_label": None,
                    period_column: 30.0,
                },
                {
                    "concept": "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                    "dimension_label": None,
                    period_column: 38.0,
                },
                {
                    "concept": "us-gaap_IncomeTaxExpenseBenefit",
                    "dimension_label": None,
                    period_column: 8.0,
                },
                {
                    "concept": "us-gaap_InterestExpenseNonOperating",
                    "dimension_label": None,
                    period_column: 2.0,
                },
            ]
        )
        balance = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_CashAndCashEquivalentsAtCarryingValue",
                    "dimension_label": None,
                    "2024-03-30": 30.0,
                },
                {
                    "concept": "us-gaap_LongTermDebtCurrent",
                    "dimension_label": None,
                    "2024-03-30": 5.0,
                },
                {
                    "concept": "us-gaap_LongTermDebtNoncurrent",
                    "dimension_label": None,
                    "2024-03-30": 20.0,
                },
                {
                    "concept": "us-gaap_MarketableSecuritiesCurrent",
                    "dimension_label": None,
                    "2024-03-30": 4.0,
                },
                {
                    "concept": "us-gaap_OperatingLeaseLiabilityCurrent",
                    "dimension_label": None,
                    "2024-03-30": 1.0,
                },
                {
                    "concept": "us-gaap_OperatingLeaseLiabilityNoncurrent",
                    "dimension_label": None,
                    "2024-03-30": 3.0,
                },
                {
                    "concept": "us-gaap_StockholdersEquity",
                    "dimension_label": None,
                    "2024-03-30": 70.0,
                },
                {
                    "concept": "us-gaap_Assets",
                    "dimension_label": None,
                    "2024-03-30": 120.0,
                },
            ]
        )
        cash_flow = pd.DataFrame(
            [
                {
                    "concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities",
                    "dimension_label": None,
                    period_column: 50.0,
                },
                {
                    "concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
                    "dimension_label": None,
                    period_column: -7.0,
                },
                {
                    "concept": "us-gaap_DepreciationDepletionAndAmortization",
                    "dimension_label": None,
                    period_column: 6.0,
                },
                {
                    "concept": "us-gaap_ShareBasedCompensation",
                    "dimension_label": None,
                    period_column: 3.0,
                },
            ]
        )
        xbrl = SimpleNamespace(
            statements=SimpleNamespace(
                income_statement=lambda: SimpleNamespace(to_dataframe=lambda: income),
                balance_sheet=lambda: SimpleNamespace(to_dataframe=lambda: balance),
                cash_flow_statement=lambda: SimpleNamespace(to_dataframe=lambda: cash_flow),
            )
        )
        filing = FakeFiling()
        filing.form = "10-Q"
        filing.period_of_report = report_end
        filing.xbrl = lambda: xbrl
        provider = EdgarProvider(
            identity="Investement Research research@example.com",
            company_factory=lambda symbol: FakeCompany(symbol, [filing]),
            clock=lambda: datetime(2024, 4, 2, tzinfo=UTC),
        )
        snapshot = provider.latest_fundamentals(
            "AAPL",
            limit=1,
            available_before=datetime(2024, 4, 1, tzinfo=UTC),
        )[0]
        self.assertEqual(snapshot.revenue, 200.0)
        self.assertEqual(snapshot.capital_expenditure, 7.0)
        self.assertEqual(snapshot.free_cash_flow, 43.0)
        self.assertEqual(snapshot.total_debt, 25.0)
        self.assertEqual(snapshot.net_income, 30.0)
        self.assertEqual(snapshot.interest_expense, 2.0)
        self.assertEqual(snapshot.short_term_investments, 4.0)
        self.assertEqual(snapshot.operating_lease_liabilities, 4.0)
        self.assertEqual(snapshot.total_equity, 70.0)
        self.assertEqual(snapshot.depreciation_and_amortization, 6.0)
        self.assertEqual(snapshot.period_basis, "fiscal-ytd")
        self.assertEqual(snapshot.provenance.metadata["accession_number"], "0001-24-000001")

    def test_yfinance_normalizes_fund_and_option_data(self):
        funds = SimpleNamespace(
            quote_type=lambda: "ETF",
            fund_overview={"categoryName": "Large Blend", "family": "Example"},
            fund_operations=pd.DataFrame(
                {"SPY": [0.09, 500_000.0]},
                index=["Annual Report Expense Ratio", "Net Assets"],
            ),
            asset_classes={"stockPosition": 99.5, "cashPosition": 0.5},
            sector_weightings={"technology": 0.30},
            top_holdings=pd.DataFrame(
                {"Name": ["Apple Inc."], "Holding Percent": [0.07]},
                index=["AAPL"],
            ),
            description="Example index fund",
        )
        option_frame = pd.DataFrame(
            [
                {
                    "contractSymbol": "SPY240621C00500000",
                    "lastTradeDate": datetime(2024, 1, 3, tzinfo=UTC),
                    "strike": 500.0,
                    "bid": 2.0,
                    "ask": 2.1,
                    "lastPrice": 2.05,
                    "impliedVolatility": 0.2,
                    "openInterest": 100,
                    "volume": 10,
                    "inTheMoney": False,
                    "currency": "USD",
                    "contractSize": "REGULAR",
                }
            ]
        )
        ticker = SimpleNamespace(
            funds_data=funds,
            options=("2024-06-21",),
            option_chain=lambda expiration: SimpleNamespace(
                calls=option_frame,
                puts=pd.DataFrame(),
            ),
        )
        provider = YFinanceProvider(
            ticker_factory=lambda symbol: ticker,
            clock=lambda: datetime(2024, 1, 3, 18, tzinfo=UTC),
        )
        as_of = datetime(2024, 1, 3, 17, tzinfo=UTC)
        fund = provider.fund_snapshot("SPY", as_of)
        chain = provider.option_chain("SPY", date(2024, 6, 21), as_of)
        self.assertEqual(fund.instrument_type, InstrumentType.ETF)
        self.assertAlmostEqual(fund.expense_ratio, 0.09)
        self.assertEqual(fund.net_assets, 500_000_000_000.0)
        self.assertAlmostEqual(fund.asset_classes["stockPosition"], 0.995)
        self.assertEqual(fund.top_holdings[0].symbol, "AAPL")
        self.assertEqual(chain.contracts[0].option_type, "call")

    def test_alpha_vantage_normalizes_daily_prices_and_reconciles(self):
        payload = {
            "Time Series (Daily)": {
                "2024-01-03": {
                    "1. open": "101",
                    "2. high": "103",
                    "3. low": "100",
                    "4. close": "102",
                    "5. volume": "1200",
                }
            }
        }
        secondary = AlphaVantageProvider(
            "test-key",
            requester=lambda url, params: payload,
            clock=lambda: datetime(2024, 1, 5, tzinfo=UTC),
        )
        secondary_bars = secondary.history("AAPL", date(2024, 1, 1), date(2024, 1, 4))
        self.assertEqual(secondary_bars[0].close, 102.0)
        primary = FakeMarketDataProvider(
            (
                PriceBar(
                    symbol="AAPL",
                    timestamp=datetime(2024, 1, 3, tzinfo=UTC),
                    open=101,
                    high=103,
                    low=100,
                    close=102.5,
                    adjusted_close=102.5,
                    volume=1200,
                    currency="USD",
                    provenance=DataProvenance(
                        source="primary",
                        retrieved_at=datetime(2024, 1, 5, tzinfo=UTC),
                        available_at=datetime(2024, 1, 4, tzinfo=UTC),
                    ),
                ),
            )
        )
        reconciled = ReconciledMarketDataProvider(primary, secondary, relative_tolerance=0.001)
        bars = reconciled.history("AAPL", date(2024, 1, 1), date(2024, 1, 4))
        self.assertEqual(bars[0].close, 102.5)
        self.assertEqual(reconciled.last_reconciliation.overlap_count, 1)
        self.assertEqual(len(reconciled.last_reconciliation.discrepancies), 1)

    def test_market_data_cache_reuses_normalized_bars(self):
        now = datetime(2024, 1, 3, tzinfo=UTC)
        provenance = DataProvenance(
            source="test",
            retrieved_at=now,
            available_at=datetime(2024, 1, 2, tzinfo=UTC),
            raw_reference="fixture",
            adjustments=("split-adjusted",),
            metadata={"currency": "USD"},
        )
        bar = PriceBar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            open=100.0,
            high=103.0,
            low=99.0,
            close=102.0,
            adjusted_close=101.5,
            volume=1000,
            currency="USD",
            provenance=provenance,
        )
        provider = FakeMarketDataProvider((bar,))
        with TemporaryDirectory() as directory:
            cached = CachedMarketDataProvider(
                provider,
                JsonPriceBarCache(Path(directory), ttl=timedelta(hours=1)),
                clock=lambda: now,
            )
            first = cached.history("aapl", date(2024, 1, 1), date(2024, 1, 3))
            second = cached.history("AAPL", date(2024, 1, 1), date(2024, 1, 3))

        self.assertEqual(provider.calls, 1)
        self.assertEqual(first, second)
        self.assertEqual(second[0].provenance.metadata, {"currency": "USD"})


if __name__ == "__main__":
    unittest.main()
