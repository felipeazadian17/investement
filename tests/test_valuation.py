import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from investement.domain import SignalAction
from investement.valuation import (
    ComparableObservation,
    DCFInputs,
    InsufficientComparablePeers,
    LTMFundamentals,
    PeerProfile,
    PeerSelectionConfig,
    comparable_observation_from_fundamentals,
    comparable_target_from_fundamentals,
    discounted_cash_flow,
    peer_profile_from_fundamentals,
    project_cash_flows,
    select_comparable_peers,
    sensitivity_matrix,
    valuation_signal,
    value_from_comparables,
)


class ValuationTests(unittest.TestCase):
    def test_dcf_matches_explicit_formula(self):
        result = discounted_cash_flow(
            DCFInputs(
                projected_free_cash_flows=(100.0, 110.0),
                discount_rate=0.10,
                terminal_growth_rate=0.02,
                net_debt=50.0,
                diluted_shares=10.0,
            )
        )
        expected_interim = 100 / 1.1 + 110 / (1.1**2)
        expected_terminal = (110 * 1.02 / (0.10 - 0.02)) / (1.1**2)
        self.assertAlmostEqual(result.enterprise_value, expected_interim + expected_terminal)
        self.assertAlmostEqual(result.value_per_share, (result.enterprise_value - 50) / 10)
        self.assertGreater(result.terminal_value_share, 0.5)

    def test_dcf_rejects_non_economic_terminal_assumption(self):
        with self.assertRaises(ValueError):
            DCFInputs((100.0,), 0.03, 0.03, 0.0, 10.0)

    def test_projection_and_sensitivity_are_monotonic(self):
        projected = project_cash_flows(100.0, (0.10, 0.05))
        self.assertEqual(projected, (110.00000000000001, 115.50000000000001))
        matrix = sensitivity_matrix(projected, (0.08, 0.10), (0.02,), 0.0, 10.0)
        self.assertGreater(matrix[0.08][0.02], matrix[0.10][0.02])

    def test_comparables_use_robust_median_and_remove_outlier(self):
        observations = [
            ComparableObservation("A", 10.0, "PE"),
            ComparableObservation("B", 11.0, "PE"),
            ComparableObservation("C", 12.0, "PE"),
            ComparableObservation("D", 100.0, "PE"),
        ]
        result = value_from_comparables(2.0, observations, "pe")
        self.assertEqual(result.selected_multiple, 11.0)
        self.assertEqual(result.value_per_share, 22.0)
        self.assertEqual(result.excluded_outliers, ("D",))
        self.assertEqual(result.selected_peers, ("A", "B", "C"))

    def test_peer_selection_uses_economic_similarity_before_multiples(self):
        target = _peer_profile("TARGET")
        observations = [
            ComparableObservation(
                symbol,
                multiple,
                "P/FCF",
                replace(target, symbol=symbol),
            )
            for symbol, multiple in (
                ("CLOSE1", 250.0),
                ("CLOSE2", 11.0),
                ("CLOSE3", 12.0),
                ("CLOSE4", 13.0),
                ("CLOSE5", 14.0),
                ("CLOSE6", 15.0),
            )
        ]
        observations.extend(
            (
                ComparableObservation(
                    "BANK",
                    9.0,
                    "P/FCF",
                    replace(target, symbol="BANK", company_type="bank"),
                ),
                ComparableObservation(
                    "STARTUP",
                    8.0,
                    "P/FCF",
                    replace(target, symbol="STARTUP", lifecycle="early-stage"),
                ),
            )
        )

        selection = select_comparable_peers(target, observations, "P/FCF")

        self.assertEqual(len(selection.selected), 6)
        self.assertIn("CLOSE1", {item.symbol for item in selection.selected})
        self.assertEqual(
            {item.symbol for item in selection.rejected},
            {"BANK", "STARTUP"},
        )
        result = value_from_comparables(2.0, selection.observations, "P/FCF")
        self.assertEqual(result.selected_multiple, 13.0)
        self.assertEqual(result.excluded_outliers, ("CLOSE1",))

    def test_peer_selection_enforces_point_in_time_cutoff(self):
        cutoff = datetime(2026, 7, 1, tzinfo=UTC)
        target = replace(_peer_profile("TARGET"), as_of=cutoff)
        observations = [
            ComparableObservation(
                symbol,
                10.0 + index,
                "P/E",
                replace(
                    target,
                    symbol=symbol,
                    as_of=cutoff + (timedelta(days=1) if symbol == "FUTURE" else timedelta()),
                ),
            )
            for index, symbol in enumerate(("A", "B", "FUTURE"))
        ]
        selection = select_comparable_peers(
            target,
            observations,
            "P/E",
            PeerSelectionConfig(minimum_peers=2, as_of=cutoff),
        )
        self.assertEqual(tuple(item.symbol for item in selection.selected), ("A", "B"))
        self.assertEqual(selection.rejected[0].symbol, "FUTURE")
        self.assertIn("cutoff", selection.rejected[0].reason)

    def test_peer_selection_refuses_to_force_too_small_group(self):
        target = _peer_profile("TARGET")
        observations = (
            ComparableObservation("A", 10.0, "P/E", replace(target, symbol="A")),
            ComparableObservation("B", 11.0, "P/E", replace(target, symbol="B")),
        )
        with self.assertRaises(InsufficientComparablePeers) as caught:
            select_comparable_peers(target, observations, "P/E")
        self.assertEqual(len(caught.exception.result.selected), 2)

    def test_peer_selection_rejects_ev_ebitda_for_banks(self):
        target = replace(_peer_profile("BANK"), company_type="bank", sector="Financials")
        with self.assertRaisesRegex(ValueError, "not appropriate"):
            select_comparable_peers(target, (), "EV/EBITDA")

    def test_peer_profile_and_multiple_are_built_from_ltm_fundamentals(self):
        previous = _ltm("TARGET", revenue=900.0, ebit=130.0, net_income=85.0)
        current = _ltm("TARGET", revenue=1_000.0, ebit=150.0, net_income=100.0)

        profile = peer_profile_from_fundamentals(
            current,
            latest_price=20.0,
            company_type="operating-company",
            sector="Industrials",
            sub_industry="Machinery",
            country="US",
            previous=previous,
            beta=1.1,
            annual_volatility=0.24,
        )
        observation = comparable_observation_from_fundamentals(profile, current, "EV/EBITDA")
        target = comparable_target_from_fundamentals(current, "EV/EBITDA")

        self.assertAlmostEqual(profile.metrics["market_cap"], 200.0)
        self.assertAlmostEqual(profile.metrics["enterprise_value"], 250.0)
        self.assertAlmostEqual(profile.metrics["revenue_growth"], 1_000 / 900 - 1)
        self.assertAlmostEqual(profile.metrics["ebit_margin"], 0.15)
        self.assertAlmostEqual(profile.metrics["roic"], 120 / 450)
        self.assertAlmostEqual(observation.multiple, 1.25)
        self.assertAlmostEqual(target.target_metric_value, 20.0)
        self.assertAlmostEqual(target.enterprise_to_equity_adjustment_per_share, -5.0)
        valuation = value_from_comparables(
            target.target_metric_value,
            (
                observation,
                replace(observation, symbol="PEER", profile=replace(profile, symbol="PEER")),
            ),
            "EV/EBITDA",
            enterprise_to_equity_adjustment_per_share=(
                target.enterprise_to_equity_adjustment_per_share
            ),
        )
        self.assertAlmostEqual(valuation.implied_enterprise_value_per_share, 25.0)
        self.assertAlmostEqual(valuation.value_per_share, 20.0)

    def test_enterprise_value_multiple_requires_equity_bridge(self):
        observations = (
            ComparableObservation("A", 10.0, "EV/EBIT"),
            ComparableObservation("B", 11.0, "EV/EBIT"),
        )
        with self.assertRaisesRegex(ValueError, "EV-to-equity bridge"):
            value_from_comparables(2.0, observations, "EV/EBIT")

    def test_margin_of_safety_drives_structured_action(self):
        buy = valuation_signal(70.0, 100.0, confidence=0.8)
        sell = valuation_signal(130.0, 100.0, confidence=0.8)
        self.assertEqual(buy.action, SignalAction.BUY)
        self.assertAlmostEqual(buy.margin_of_safety, 0.30)
        self.assertEqual(sell.action, SignalAction.SELL)


def _peer_profile(symbol: str) -> PeerProfile:
    return PeerProfile(
        symbol=symbol,
        company_type="operating-company",
        sector="Information Technology",
        industry="Software",
        sub_industry="Application Software",
        country="US",
        accounting_standard="US GAAP",
        lifecycle="mature",
        business_model="subscription",
        revenue_mix={"software": 0.85, "services": 0.15},
        metrics={
            "revenue_growth": 0.08,
            "ebit_growth": 0.09,
            "fcf_growth": 0.10,
            "gross_margin": 0.72,
            "ebitda_margin": 0.31,
            "ebit_margin": 0.27,
            "net_margin": 0.22,
            "roic": 0.18,
            "roe": 0.24,
            "cash_conversion": 1.05,
            "capex_to_revenue": 0.04,
            "asset_turnover": 0.70,
            "working_capital_to_revenue": 0.03,
            "revenue": 10_000_000_000.0,
            "enterprise_value": 80_000_000_000.0,
            "market_cap": 75_000_000_000.0,
            "total_assets": 30_000_000_000.0,
            "net_debt_to_ebitda": 0.5,
            "interest_coverage": 15.0,
            "beta": 1.0,
            "annual_volatility": 0.25,
            "revenue_cyclicality": 0.10,
            "sbc_to_revenue": 0.04,
        },
    )


def _ltm(
    symbol: str,
    *,
    revenue: float,
    ebit: float,
    net_income: float,
) -> LTMFundamentals:
    return LTMFundamentals(
        symbol=symbol,
        period_start=date(2025, 4, 1),
        period_end=date(2026, 3, 31),
        available_at=datetime(2026, 5, 1, tzinfo=UTC),
        currency="USD",
        industry_code="3560",
        revenue=revenue,
        ebit=ebit,
        operating_cash_flow=150.0,
        capital_expenditure=30.0,
        net_income=net_income,
        pretax_income=125.0,
        income_tax_expense=25.0,
        interest_expense=10.0,
        depreciation_and_amortization=50.0,
        stock_based_compensation=5.0,
        diluted_shares=10.0,
        current_shares_outstanding=10.0,
        total_debt=100.0,
        cash_and_equivalents=50.0,
        short_term_investments=0.0,
        long_term_investments=0.0,
        operating_lease_liabilities=0.0,
        preferred_stock=0.0,
        noncontrolling_interest=0.0,
        pension_liabilities=0.0,
        total_equity=400.0,
        total_assets=800.0,
        source_filings=("fixture",),
    )


if __name__ == "__main__":
    unittest.main()
