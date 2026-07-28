import importlib.util
import inspect
import os
import unittest

from investement.backtesting import QuantStatsMetrics, VectorbtSingleAsset
from investement.portfolio import (
    PortfolioConstraints,
    PortfolioRequest,
    RobustPortfolioOptimizer,
)


def available(module):
    return importlib.util.find_spec(module) is not None


SYNTHETIC_REQUEST = PortfolioRequest(
    returns={
        "A": (0.010, 0.012, -0.005, 0.008, 0.004, -0.002),
        "B": (0.002, 0.001, 0.003, -0.001, 0.002, 0.001),
        "C": (-0.004, 0.006, 0.005, 0.003, -0.002, 0.007),
    },
    constraints=PortfolioConstraints(max_weight=0.60, min_cash=0.10),
)


class OptionalAdapterTests(unittest.TestCase):
    @unittest.skipUnless(available("pypfopt"), "PyPortfolioOpt is not installed")
    def test_pypfopt_backend(self):
        result = RobustPortfolioOptimizer().optimize(SYNTHETIC_REQUEST, backend="pypfopt")
        self.assertEqual(result.backend, "pypfopt")
        self.assertAlmostEqual(sum(result.weights.values()), 0.90)

    @unittest.skipUnless(available("riskfolio"), "Riskfolio is not installed")
    def test_riskfolio_backend(self):
        result = RobustPortfolioOptimizer().optimize(SYNTHETIC_REQUEST, backend="riskfolio")
        self.assertEqual(result.backend, "riskfolio")
        self.assertAlmostEqual(sum(result.weights.values()), 0.90)

    @unittest.skipUnless(available("quantstats"), "QuantStats is not installed")
    def test_quantstats_backend(self):
        metrics = QuantStatsMetrics().compute((0.01, -0.005, 0.02, 0.003))
        self.assertIn("sharpe", metrics)
        self.assertIn("max_drawdown", metrics)

    @unittest.skipUnless(available("vectorbt"), "vectorbt is not installed")
    def test_vectorbt_backend(self):
        stats = VectorbtSingleAsset().run(
            prices=(100.0, 101.0, 103.0, 102.0),
            entries=(True, False, False, False),
            exits=(False, False, True, False),
            fees=0.0001,
            slippage=0.0001,
        )
        self.assertIn("Total Return [%]", stats)

    @unittest.skipUnless(available("yfinance"), "yfinance is not installed")
    def test_yfinance_download_signature_matches_adapter(self):
        import yfinance as yf

        parameters = inspect.signature(yf.download).parameters
        self.assertIn("auto_adjust", parameters)
        self.assertIn("multi_level_index", parameters)

    @unittest.skipUnless(available("edgar"), "EdgarTools is not installed")
    def test_edgartools_company_api_matches_adapter(self):
        os.environ["EDGAR_LOCAL_DATA_DIR"] = "/tmp/investement-edgar-data"
        os.environ["EDGAR_CACHE_DIR"] = "/tmp/investement-edgar-cache"
        from edgar import Company, set_identity

        self.assertTrue(callable(Company))
        self.assertTrue(callable(set_identity))
        parameters = inspect.signature(Company.get_filings).parameters
        self.assertIn("filing_date", parameters)
        self.assertIn("amendments", parameters)

    @unittest.skipUnless(available("schwab"), "schwab-py is not installed")
    def test_schwab_auth_and_account_api_match_facade(self):
        from schwab.auth import easy_client
        from schwab.client import Client

        auth_parameters = inspect.signature(easy_client).parameters
        self.assertTrue(
            {"api_key", "app_secret", "callback_url", "token_path"} <= auth_parameters.keys()
        )
        self.assertEqual(Client.Account.Fields.POSITIONS.value, "positions")


if __name__ == "__main__":
    unittest.main()
