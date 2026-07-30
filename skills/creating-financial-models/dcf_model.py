"""Auditable FCFF DCF adapter backed by the production valuation engine.

This resource performs calculations only. Callers must source point-in-time
filings and dated market inputs before constructing the model.
"""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from investement.valuation import (
    DCFInputs,
    OperatingProjectionInputs,
    discounted_cash_flow,
    operating_sensitivity_matrix,
    project_operating_fcff,
    validate_terminal_growth,
)


@dataclass(frozen=True)
class MarketCapitalInputs:
    risk_free_rate: float
    equity_risk_premium: float
    adjusted_beta: float
    pretax_cost_of_debt: float
    marginal_tax_rate: float
    market_equity: float
    debt_and_leases: float
    observed_at: str
    source: str

    def __post_init__(self) -> None:
        values = (
            self.risk_free_rate,
            self.equity_risk_premium,
            self.adjusted_beta,
            self.pretax_cost_of_debt,
            self.marginal_tax_rate,
            self.market_equity,
            self.debt_and_leases,
        )
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("market capital inputs must be finite")
        if not 0 < self.risk_free_rate < 1:
            raise ValueError("risk_free_rate must be between zero and one")
        if not 0 < self.equity_risk_premium < 1:
            raise ValueError("equity_risk_premium must be between zero and one")
        if not 0 <= self.pretax_cost_of_debt < 1:
            raise ValueError("pretax_cost_of_debt must be between zero and one")
        if not 0 <= self.marginal_tax_rate < 1:
            raise ValueError("marginal_tax_rate must be between zero and one")
        if self.market_equity <= 0 or self.debt_and_leases < 0:
            raise ValueError("market equity must be positive and debt cannot be negative")
        if not self.observed_at.strip() or not self.source.strip():
            raise ValueError("dated market provenance is required")

    @property
    def cost_of_equity(self) -> float:
        return self.risk_free_rate + self.adjusted_beta * self.equity_risk_premium

    @property
    def after_tax_cost_of_debt(self) -> float:
        return self.pretax_cost_of_debt * (1 - self.marginal_tax_rate)

    @property
    def wacc(self) -> float:
        total = self.market_equity + self.debt_and_leases
        equity_weight = self.market_equity / total
        debt_weight = self.debt_and_leases / total
        result = (
            equity_weight * self.cost_of_equity
            + debt_weight * self.after_tax_cost_of_debt
        )
        if not 0 < result < 1:
            raise ValueError("calculated WACC is not economically valid")
        return result


@dataclass(frozen=True)
class EquityBridgeInputs:
    debt: float
    operating_lease_liabilities: float
    preferred_stock: float
    noncontrolling_interest: float
    pension_liabilities: float
    cash_and_equivalents: float
    short_term_investments: float
    long_term_investments: float

    def __post_init__(self) -> None:
        if any(value < 0 or not isfinite(value) for value in asdict(self).values()):
            raise ValueError("equity bridge values must be finite and non-negative")

    @property
    def net_debt_equivalent(self) -> float:
        claims = (
            self.debt
            + self.operating_lease_liabilities
            + self.preferred_stock
            + self.noncontrolling_interest
            + self.pension_liabilities
        )
        nonoperating_assets = (
            self.cash_and_equivalents
            + self.short_term_investments
            + self.long_term_investments
        )
        return claims - nonoperating_assets


class DCFModel:
    """Thin stateful adapter around the tested FCFF projection functions."""

    def __init__(self, company_name: str = "Company") -> None:
        self.company_name = company_name
        self.market_inputs: MarketCapitalInputs | None = None
        self.projection_inputs: OperatingProjectionInputs | None = None
        self.bridge: EquityBridgeInputs | None = None
        self.shares: float | None = None
        self.results: dict[str, Any] = {}

    def configure(
        self,
        market_inputs: MarketCapitalInputs,
        projection_inputs: OperatingProjectionInputs,
        bridge: EquityBridgeInputs,
        diluted_shares: float,
    ) -> None:
        if diluted_shares <= 0 or not isfinite(diluted_shares):
            raise ValueError("diluted_shares must be positive and finite")
        if projection_inputs.tax_rate != market_inputs.marginal_tax_rate:
            raise ValueError("projection and WACC tax rates must match")
        validate_terminal_growth(
            projection_inputs.terminal_growth_rate,
            market_inputs.wacc,
            market_inputs.risk_free_rate,
            projection_inputs.stable_roic,
        )
        self.market_inputs = market_inputs
        self.projection_inputs = projection_inputs
        self.bridge = bridge
        self.shares = diluted_shares

    def calculate(self) -> dict[str, Any]:
        market, assumptions, bridge, shares = self._configured()
        projection = project_operating_fcff(assumptions)
        valuation = discounted_cash_flow(
            DCFInputs(
                projected_free_cash_flows=projection.free_cash_flows,
                discount_rate=market.wacc,
                terminal_growth_rate=assumptions.terminal_growth_rate,
                net_debt=bridge.net_debt_equivalent,
                diluted_shares=shares,
                terminal_cash_flow=projection.terminal_cash_flow(
                    assumptions.terminal_growth_rate
                ),
            )
        )
        sensitivity = operating_sensitivity_matrix(
            projection=projection,
            discount_rates=_axis(market.wacc, 0.01, 2),
            terminal_growth_rates=_axis(
                assumptions.terminal_growth_rate,
                0.005,
                2,
                floor=0.0,
            ),
            net_debt=bridge.net_debt_equivalent,
            diluted_shares=shares,
            risk_free_rate=market.risk_free_rate,
        )
        self.results = {
            "company": self.company_name,
            "market_inputs": asdict(market),
            "wacc": market.wacc,
            "projection_inputs": asdict(assumptions),
            "projection": [asdict(item) for item in projection.years],
            "enterprise_value": valuation.enterprise_value,
            "equity_value": valuation.equity_value,
            "value_per_share": valuation.value_per_share,
            "terminal_value_share": valuation.terminal_value_share,
            "equity_bridge": asdict(bridge),
            "net_debt_equivalent": bridge.net_debt_equivalent,
            "sensitivity": sensitivity,
        }
        return self.results

    def _configured(
        self,
    ) -> tuple[
        MarketCapitalInputs,
        OperatingProjectionInputs,
        EquityBridgeInputs,
        float,
    ]:
        if (
            self.market_inputs is None
            or self.projection_inputs is None
            or self.bridge is None
            or self.shares is None
        ):
            raise ValueError("configure the model with explicit inputs before calculating")
        return self.market_inputs, self.projection_inputs, self.bridge, self.shares


def fcff_from_cash_flow_statement(
    operating_cash_flow: float,
    capex: float,
    interest_expense: float,
    marginal_tax_rate: float,
) -> float:
    """Bridge levered US-GAAP CFO to FCFF for a cash-conversion cross-check."""
    values = (operating_cash_flow, capex, interest_expense, marginal_tax_rate)
    if any(not isfinite(float(value)) for value in values):
        raise ValueError("FCFF bridge inputs must be finite")
    if capex < 0 or interest_expense < 0 or not 0 <= marginal_tax_rate < 1:
        raise ValueError("capex/interest must be non-negative and tax rate valid")
    return operating_cash_flow - capex + interest_expense * (1 - marginal_tax_rate)


def _axis(center: float, step: float, radius: int, floor: float = 0.0001) -> tuple[float, ...]:
    return tuple(max(floor, center + offset * step) for offset in range(-radius, radius + 1))


if __name__ == "__main__":
    model = DCFModel("ExampleCo")
    market = MarketCapitalInputs(
        risk_free_rate=0.04,
        equity_risk_premium=0.05,
        adjusted_beta=1.10,
        pretax_cost_of_debt=0.055,
        marginal_tax_rate=0.21,
        market_equity=900.0,
        debt_and_leases=100.0,
        observed_at="2026-07-01",
        source="example dated market observations",
    )
    projection = OperatingProjectionInputs(
        base_revenue=500.0,
        initial_revenue_growth=0.12,
        base_ebit_margin=0.18,
        stable_ebit_margin=0.17,
        tax_rate=0.21,
        current_roic=0.16,
        stable_roic=market.wacc,
        terminal_growth_rate=0.025,
        years=7,
    )
    bridge = EquityBridgeInputs(
        debt=90.0,
        operating_lease_liabilities=10.0,
        preferred_stock=0.0,
        noncontrolling_interest=0.0,
        pension_liabilities=0.0,
        cash_and_equivalents=30.0,
        short_term_investments=10.0,
        long_term_investments=0.0,
    )
    model.configure(market, projection, bridge, diluted_shares=50.0)
    output = model.calculate()
    print(
        {
            "value_per_share": round(output["value_per_share"], 2),
            "wacc": round(output["wacc"], 4),
            "terminal_value_share": round(output["terminal_value_share"], 4),
        }
    )
