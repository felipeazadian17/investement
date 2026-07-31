import unittest
from datetime import UTC, date, datetime

from investement.domain import DataProvenance, FundamentalSnapshot
from investement.valuation import (
    CreditSpreadObservation,
    DamodaranCreditSpreadProvider,
    DamodaranMarketRateProvider,
    DatedCreditSpreadProvider,
    DatedMarketRateProvider,
    DCFInputs,
    MarketRateObservation,
    OperatingProjectionInputs,
    build_ltm_fundamentals,
    discounted_cash_flow,
    operating_sensitivity_matrix,
    project_operating_fcff,
    synthetic_default_spread,
    validate_terminal_growth,
)


class FundamentalValuationTests(unittest.TestCase):
    def test_dated_market_inputs_select_latest_observation_before_cutoff(self):
        rates = DatedMarketRateProvider(
            (
                MarketRateObservation(date(2022, 12, 31), 0.038, 0.059, "fixture://2022"),
                MarketRateObservation(date(2023, 12, 31), 0.039, 0.046, "fixture://2023"),
            )
        )
        spreads = DatedCreditSpreadProvider(
            (
                CreditSpreadObservation(
                    date(2023, 1, 1), ((float("inf"), 0.01),), "fixture://spreads-2023"
                ),
                CreditSpreadObservation(
                    date(2024, 1, 1), ((float("inf"), 0.008),), "fixture://spreads-2024"
                ),
            )
        )
        cutoff = datetime(2023, 6, 30, tzinfo=UTC)

        self.assertEqual(rates.rates(cutoff).source_url, "fixture://2022")
        self.assertEqual(spreads.spreads(cutoff).source_url, "fixture://spreads-2023")
        with self.assertRaisesRegex(ValueError, "available"):
            rates.rates(datetime(2020, 1, 1, tzinfo=UTC))

    def test_ltm_uses_fy_plus_current_ytd_minus_prior_ytd(self):
        annual = _snapshot(
            date(2024, 1, 1),
            date(2024, 12, 31),
            "10-K",
            revenue=1000.0,
            ebit=200.0,
            operating_cash_flow=160.0,
            capital_expenditure=40.0,
            interest_expense=10.0,
            diluted_shares=10.0,
        )
        current_ytd = _snapshot(
            date(2025, 1, 1),
            date(2025, 6, 30),
            "10-Q",
            revenue=600.0,
            ebit=130.0,
            operating_cash_flow=100.0,
            capital_expenditure=25.0,
            interest_expense=6.0,
            diluted_shares=9.5,
            total_debt=90.0,
            cash_and_equivalents=30.0,
            short_term_investments=10.0,
            long_term_investments=5.0,
            operating_lease_liabilities=8.0,
            preferred_stock=2.0,
            noncontrolling_interest=3.0,
            pension_liabilities=4.0,
            current_shares_outstanding=9.4,
        )
        prior_ytd = _snapshot(
            date(2024, 1, 1),
            date(2024, 6, 30),
            "10-Q",
            revenue=550.0,
            ebit=110.0,
            operating_cash_flow=80.0,
            capital_expenditure=20.0,
            interest_expense=5.0,
            diluted_shares=10.5,
        )
        ltm = build_ltm_fundamentals(
            (current_ytd, annual, prior_ytd),
            datetime(2025, 8, 1, tzinfo=UTC),
        )
        self.assertEqual(ltm.revenue, 1050.0)
        self.assertEqual(ltm.ebit, 220.0)
        self.assertEqual(ltm.operating_cash_flow, 180.0)
        self.assertEqual(ltm.capital_expenditure, 45.0)
        self.assertEqual(ltm.interest_expense, 11.0)
        self.assertAlmostEqual(ltm.fcff(0.25), 143.25)
        self.assertAlmostEqual(ltm.equity_bridge.net_debt_equivalent, 62.0)
        self.assertGreater(ltm.diluted_shares, 9.0)
        self.assertLess(ltm.diluted_shares, 11.0)

    def test_operating_projection_ties_terminal_growth_to_reinvestment(self):
        projection = project_operating_fcff(
            OperatingProjectionInputs(
                base_revenue=1000.0,
                initial_revenue_growth=0.30,
                base_ebit_margin=0.12,
                stable_ebit_margin=0.18,
                tax_rate=0.21,
                current_roic=0.25,
                stable_roic=0.09,
                terminal_growth_rate=0.025,
                years=7,
            )
        )
        self.assertEqual(projection.years[0].revenue_growth, 0.30)
        self.assertAlmostEqual(projection.years[-1].revenue_growth, 0.025)
        self.assertAlmostEqual(projection.years[-1].roic, 0.09)
        terminal_cash_flow = projection.terminal_cash_flow(0.025)
        self.assertAlmostEqual(
            terminal_cash_flow,
            projection.terminal_nopat * (1 - 0.025 / 0.09),
        )
        result = discounted_cash_flow(
            DCFInputs(
                projection.free_cash_flows,
                0.09,
                0.025,
                net_debt=100.0,
                diluted_shares=10.0,
                terminal_cash_flow=terminal_cash_flow,
            )
        )
        self.assertGreater(result.enterprise_value, 0)

    def test_terminal_validation_and_sensitivity_reject_non_economic_cells(self):
        projection = project_operating_fcff(
            OperatingProjectionInputs(100.0, 0.10, 0.20, 0.20, 0.21, 0.15, 0.08, 0.02, 5)
        )
        with self.assertRaises(ValueError):
            validate_terminal_growth(0.05, 0.09, 0.04, 0.08)
        matrix = operating_sensitivity_matrix(
            projection,
            (0.03, 0.08, 0.10),
            (0.02, 0.04),
            net_debt=0.0,
            diluted_shares=10.0,
            risk_free_rate=0.04,
        )
        self.assertIsNone(matrix[0.03][0.04])
        self.assertGreater(matrix[0.08][0.02], matrix[0.10][0.02])

    def test_market_rate_page_and_synthetic_credit_spread_are_dated(self):
        html = """
        Implied ERP on July 1, 2026 = 4.<span></span>18%
        (with the US treasury rate of 4.45% used as the riskfree rate in US dollars)
        """
        provider = DamodaranMarketRateProvider(loader=lambda url: html)
        rates = provider.rates(datetime(2026, 7, 1, tzinfo=UTC))
        self.assertEqual(rates.observed_at, date(2026, 7, 1))
        self.assertAlmostEqual(rates.equity_risk_premium, 0.0418)
        self.assertAlmostEqual(rates.risk_free_rate, 0.0445)
        self.assertAlmostEqual(synthetic_default_spread(9.0, 100.0), 0.004)
        self.assertAlmostEqual(synthetic_default_spread(1.0, 100.0), 0.0885)

        rows = "".join(
            f"<tr><td>{index}</td><td>{index + 1}</td><td>A</td>"
            f"<td>{10 - index}%</td></tr>"
            for index in range(10)
        )
        credit_html = f"Data used is as of January 2026<table>{rows}</table>"
        spreads = DamodaranCreditSpreadProvider(
            loader=lambda url: credit_html
        ).spreads(datetime(2026, 7, 1, tzinfo=UTC))
        self.assertEqual(spreads.observed_at, date(2026, 1, 1))
        self.assertAlmostEqual(spreads.spread(0.5), 0.10)
        self.assertAlmostEqual(spreads.spread(99.0), 0.01)


def _snapshot(period_start, period_end, filing_type, **overrides):
    available_at = datetime(period_end.year, min(period_end.month + 1, 12), 15, tzinfo=UTC)
    values = {
        "symbol": "TEST",
        "period_start": period_start,
        "period_end": period_end,
        "period_basis": "fiscal-year" if filing_type == "10-K" else "fiscal-ytd",
        "filing_type": filing_type,
        "currency": "USD",
        "revenue": 100.0,
        "ebit": 20.0,
        "operating_cash_flow": 15.0,
        "capital_expenditure": 5.0,
        "cash_and_equivalents": 20.0,
        "total_debt": 50.0,
        "diluted_shares": 10.0,
        "net_income": 15.0,
        "pretax_income": 20.0,
        "income_tax_expense": 4.2,
        "interest_expense": 2.0,
        "total_equity": 80.0,
        "total_assets": 150.0,
        "provenance": DataProvenance(
            source="sec-edgar-xbrl",
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            available_at=available_at,
            metadata={"accession_number": f"{filing_type}-{period_end}"},
        ),
    }
    values.update(overrides)
    return FundamentalSnapshot(**values)


if __name__ == "__main__":
    unittest.main()
