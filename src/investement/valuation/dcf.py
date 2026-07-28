from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DCFInputs:
    projected_free_cash_flows: Sequence[float]
    discount_rate: float
    terminal_growth_rate: float
    net_debt: float
    diluted_shares: float

    def __post_init__(self) -> None:
        if not self.projected_free_cash_flows:
            raise ValueError("at least one projected cash flow is required")
        for cash_flow in self.projected_free_cash_flows:
            if not isfinite(float(cash_flow)):
                raise ValueError("projected cash flows must be finite")
        if not 0 < self.discount_rate < 1:
            raise ValueError("discount_rate must be between 0 and 1")
        if self.terminal_growth_rate <= -1:
            raise ValueError("terminal_growth_rate must be greater than -1")
        if self.discount_rate <= self.terminal_growth_rate:
            raise ValueError("discount_rate must be greater than terminal_growth_rate")
        if self.diluted_shares <= 0 or not isfinite(self.diluted_shares):
            raise ValueError("diluted_shares must be positive and finite")
        if not isfinite(self.net_debt):
            raise ValueError("net_debt must be finite")


@dataclass(frozen=True)
class DCFResult:
    enterprise_value: float
    equity_value: float
    value_per_share: float
    present_value_cash_flows: float
    present_value_terminal: float
    terminal_value_share: float


def project_cash_flows(base_free_cash_flow: float, growth_rates: Iterable[float]) -> tuple:
    if not isfinite(base_free_cash_flow):
        raise ValueError("base_free_cash_flow must be finite")
    projected = []
    current = float(base_free_cash_flow)
    for growth in growth_rates:
        if not isfinite(float(growth)) or growth <= -1:
            raise ValueError("growth rates must be finite and greater than -1")
        current *= 1 + float(growth)
        projected.append(current)
    if not projected:
        raise ValueError("at least one growth rate is required")
    return tuple(projected)


def discounted_cash_flow(inputs: DCFInputs) -> DCFResult:
    rate = inputs.discount_rate
    cash_flows = tuple(float(value) for value in inputs.projected_free_cash_flows)
    present_value_cash_flows = sum(
        cash_flow / ((1 + rate) ** year) for year, cash_flow in enumerate(cash_flows, start=1)
    )
    terminal_value = (
        cash_flows[-1] * (1 + inputs.terminal_growth_rate) / (rate - inputs.terminal_growth_rate)
    )
    present_value_terminal = terminal_value / ((1 + rate) ** len(cash_flows))
    enterprise_value = present_value_cash_flows + present_value_terminal
    equity_value = enterprise_value - inputs.net_debt
    terminal_share = present_value_terminal / enterprise_value if enterprise_value else 0.0
    return DCFResult(
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        value_per_share=equity_value / inputs.diluted_shares,
        present_value_cash_flows=present_value_cash_flows,
        present_value_terminal=present_value_terminal,
        terminal_value_share=terminal_share,
    )


def sensitivity_matrix(
    projected_free_cash_flows: Sequence[float],
    discount_rates: Iterable[float],
    terminal_growth_rates: Iterable[float],
    net_debt: float,
    diluted_shares: float,
) -> Mapping[float, Mapping[float, float]]:
    rates = tuple(float(rate) for rate in discount_rates)
    growth_rates = tuple(float(growth) for growth in terminal_growth_rates)
    if not rates or not growth_rates:
        raise ValueError("sensitivity axes cannot be empty")
    matrix = {}
    for rate in rates:
        row = {}
        for growth in growth_rates:
            row[growth] = discounted_cash_flow(
                DCFInputs(
                    projected_free_cash_flows=projected_free_cash_flows,
                    discount_rate=rate,
                    terminal_growth_rate=growth,
                    net_debt=net_debt,
                    diluted_shares=diluted_shares,
                )
            ).value_per_share
        matrix[rate] = row
    return matrix
