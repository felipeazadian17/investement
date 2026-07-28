import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from investement.data import (
    CachedMarketDataProvider,
    EdgarProvider,
    JsonPriceBarCache,
    YFinanceProvider,
    normalize_symbol,
)
from investement.domain import DataProvenance, PriceBar


class FakeFrame:
    empty = False

    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        return iter(self._rows)


class FakeFiling:
    form = "10-K"
    filing_date = date(2024, 2, 1)
    accession_number = "0001-24-000001"
    primary_document = "report.htm"
    homepage_url = "https://www.sec.gov/Archives/example"

    def text(self):
        return "filing body"


class FakeFilings(list):
    def head(self, limit):
        return self[:limit]

    def latest(self):
        return self[0]


class FakeCompany:
    cik = "0000320193"

    def __init__(self, symbol):
        self.symbol = symbol
        self.calls = []

    def get_filings(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFilings([FakeFiling()])


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
        self.assertEqual(captured["tickers"], "AAPL")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].adjusted_close, 101.5)
        self.assertIsNotNone(bars[0].timestamp.tzinfo)
        self.assertLessEqual(bars[0].provenance.available_at, bars[0].provenance.retrieved_at)

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
        self.assertEqual(records[0].provenance.source, "sec-edgar")

    def test_edgar_requires_contact_identity(self):
        with self.assertRaises(ValueError):
            EdgarProvider(identity="anonymous")

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
