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
    terminal_cash_flow: float | None = None

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
        if self.terminal_cash_flow is not None and not isfinite(self.terminal_cash_flow):
            raise ValueError("terminal_cash_flow must be finite")


@dataclass(frozen=True)
class DCFResult:
    enterprise_value: float
    equity_value: float
    value_per_share: float
    present_value_cash_flows: float
    present_value_terminal: float
    terminal_value_share: float


@dataclass(frozen=True)
class OperatingProjectionInputs:
    base_revenue: float
    initial_revenue_growth: float
    base_ebit_margin: float
    stable_ebit_margin: float
    tax_rate: float
    current_roic: float
    stable_roic: float
    terminal_growth_rate: float
    years: int = 7

    def __post_init__(self) -> None:
        values = (
            self.base_revenue,
            self.initial_revenue_growth,
            self.base_ebit_margin,
            self.stable_ebit_margin,
            self.tax_rate,
            self.current_roic,
            self.stable_roic,
            self.terminal_growth_rate,
        )
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("operating projection inputs must be finite")
        if self.base_revenue <= 0 or self.years < 2:
            raise ValueError("projection requires positive revenue and at least two years")
        if self.initial_revenue_growth <= -1:
            raise ValueError("initial revenue growth must be greater than -100%")
        if not 0 <= self.tax_rate < 1:
            raise ValueError("tax_rate must be between zero and one")
        if self.current_roic <= 0 or self.stable_roic <= 0:
            raise ValueError("ROIC assumptions must be positive")
        if not 0 <= self.terminal_growth_rate < self.stable_roic:
            raise ValueError("terminal growth must be non-negative and below stable ROIC")


@dataclass(frozen=True)
class ProjectionYear:
    year: int
    revenue: float
    revenue_growth: float
    ebit_margin: float
    nopat: float
    roic: float
    reinvestment_rate: float
    free_cash_flow_to_firm: float


@dataclass(frozen=True)
class OperatingProjection:
    years: tuple[ProjectionYear, ...]
    terminal_nopat: float
    stable_roic: float

    @property
    def free_cash_flows(self) -> tuple[float, ...]:
        return tuple(item.free_cash_flow_to_firm for item in self.years)

    def terminal_cash_flow(self, terminal_growth_rate: float) -> float:
        if not 0 <= terminal_growth_rate < self.stable_roic:
            raise ValueError("terminal growth must be non-negative and below stable ROIC")
        reinvestment_rate = terminal_growth_rate / self.stable_roic
        return self.terminal_nopat * (1 - reinvestment_rate)


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
    terminal_cash_flow = inputs.terminal_cash_flow
    if terminal_cash_flow is None:
        terminal_cash_flow = cash_flows[-1] * (1 + inputs.terminal_growth_rate)
    terminal_value = terminal_cash_flow / (rate - inputs.terminal_growth_rate)
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


def project_operating_fcff(inputs: OperatingProjectionInputs) -> OperatingProjection:
    revenue = float(inputs.base_revenue)
    years = []
    for year in range(1, inputs.years + 1):
        progress = (year - 1) / (inputs.years - 1)
        growth = _fade(inputs.initial_revenue_growth, inputs.terminal_growth_rate, progress)
        margin = _fade(inputs.base_ebit_margin, inputs.stable_ebit_margin, progress)
        roic = _fade(inputs.current_roic, inputs.stable_roic, progress)
        revenue *= 1 + growth
        nopat = revenue * margin * (1 - inputs.tax_rate)
        reinvestment_rate = growth / roic
        fcff = nopat * (1 - reinvestment_rate)
        years.append(
            ProjectionYear(
                year=year,
                revenue=revenue,
                revenue_growth=growth,
                ebit_margin=margin,
                nopat=nopat,
                roic=roic,
                reinvestment_rate=reinvestment_rate,
                free_cash_flow_to_firm=fcff,
            )
        )
    terminal_nopat = years[-1].nopat * (1 + inputs.terminal_growth_rate)
    return OperatingProjection(tuple(years), terminal_nopat, inputs.stable_roic)


def validate_terminal_growth(
    terminal_growth_rate: float,
    discount_rate: float,
    risk_free_rate: float,
    stable_roic: float,
) -> None:
    values = (terminal_growth_rate, discount_rate, risk_free_rate, stable_roic)
    if any(not isfinite(float(value)) for value in values):
        raise ValueError("terminal assumptions must be finite")
    if terminal_growth_rate < 0:
        raise ValueError("a perpetual-growth terminal value cannot use negative growth")
    if terminal_growth_rate > risk_free_rate:
        raise ValueError("terminal growth cannot exceed the long-term risk-free rate")
    if terminal_growth_rate >= discount_rate:
        raise ValueError("terminal growth must be below the discount rate")
    if terminal_growth_rate >= stable_roic:
        raise ValueError("terminal growth must be below stable ROIC")


def operating_sensitivity_matrix(
    projection: OperatingProjection,
    discount_rates: Iterable[float],
    terminal_growth_rates: Iterable[float],
    net_debt: float,
    diluted_shares: float,
    risk_free_rate: float,
) -> Mapping[float, Mapping[float, float | None]]:
    rates = tuple(float(rate) for rate in discount_rates)
    growth_rates = tuple(float(growth) for growth in terminal_growth_rates)
    if not rates or not growth_rates:
        raise ValueError("sensitivity axes cannot be empty")
    matrix = {}
    for rate in rates:
        row = {}
        for growth in growth_rates:
            try:
                validate_terminal_growth(
                    growth,
                    rate,
                    risk_free_rate,
                    projection.stable_roic,
                )
            except ValueError:
                row[growth] = None
                continue
            row[growth] = discounted_cash_flow(
                DCFInputs(
                    projected_free_cash_flows=projection.free_cash_flows,
                    discount_rate=rate,
                    terminal_growth_rate=growth,
                    net_debt=net_debt,
                    diluted_shares=diluted_shares,
                    terminal_cash_flow=projection.terminal_cash_flow(growth),
                )
            ).value_per_share
        matrix[rate] = row
    return matrix


def _fade(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


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
