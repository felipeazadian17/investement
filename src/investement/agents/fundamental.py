from datetime import UTC, datetime, time
from math import tanh
from statistics import mean, median

from investement.agents.models import AssetDataSnapshot, FundamentalAnalysis
from investement.orchestration import AgentFinding, EvidenceReference
from investement.valuation import (
    DCFInputs,
    InsufficientFundamentalData,
    MarketWACCBuilder,
    OperatingProjectionInputs,
    build_ltm_fundamentals,
    discounted_cash_flow,
    operating_sensitivity_matrix,
    project_operating_fcff,
    validate_terminal_growth,
)


class UnsupportedFundamentalModel(ValueError):
    pass


class FundamentalAgent:
    name = "fundamental"

    def __init__(
        self,
        wacc_builder: MarketWACCBuilder | None = None,
        projection_years: int = 7,
        long_run_nominal_growth: float = 0.025,
        entry_buffer: float = 0.10,
    ) -> None:
        if projection_years < 5:
            raise ValueError("DCF convergence requires at least five projection years")
        if not 0 <= long_run_nominal_growth < 1:
            raise ValueError("long-run nominal growth must be between zero and one")
        if not 0 <= entry_buffer < 1:
            raise ValueError("entry buffer must be between zero and one")
        self._wacc_builder = wacc_builder
        self._projection_years = projection_years
        self._long_run_nominal_growth = long_run_nominal_growth
        self._entry_buffer = entry_buffer

    def analyze(self, snapshot: AssetDataSnapshot) -> FundamentalAnalysis:
        if self._wacc_builder is None:
            raise RuntimeError("FundamentalAgent requires a market-backed WACC builder")
        ltm = build_ltm_fundamentals(tuple(snapshot.fundamentals), snapshot.as_of)
        _validate_company_for_fcff(ltm)
        capital_cost = self._wacc_builder.build(
            snapshot.symbol,
            snapshot.as_of,
            snapshot.latest_price,
            ltm,
        )
        terminal_growth = min(
            self._long_run_nominal_growth,
            capital_cost.risk_free_rate,
        )
        stable_roic = max(capital_cost.wacc, terminal_growth + 0.005)
        validate_terminal_growth(
            terminal_growth,
            capital_cost.wacc,
            capital_cost.risk_free_rate,
            stable_roic,
        )

        revenue_growth = _historical_revenue_growth(snapshot)
        adjusted_ebit = ltm.ebit + capital_cost.lease_interest_adjustment
        operating_margin = adjusted_ebit / ltm.revenue
        stable_margin = _stable_operating_margin(snapshot, operating_margin) + (
            capital_cost.lease_interest_adjustment / ltm.revenue
        )
        invested_capital = _invested_capital(ltm)
        nopat = adjusted_ebit * (1 - capital_cost.marginal_tax_rate)
        current_roic = nopat / invested_capital
        if current_roic <= 0:
            raise UnsupportedFundamentalModel(
                "FCFF DCF requires positive normalized ROIC; use a life-cycle scenario model"
            )

        projection = project_operating_fcff(
            OperatingProjectionInputs(
                base_revenue=ltm.revenue,
                initial_revenue_growth=revenue_growth,
                base_ebit_margin=operating_margin,
                stable_ebit_margin=stable_margin,
                tax_rate=capital_cost.marginal_tax_rate,
                current_roic=current_roic,
                stable_roic=stable_roic,
                terminal_growth_rate=terminal_growth,
                years=self._projection_years,
            )
        )
        shares = ltm.share_count
        if shares is None:
            raise InsufficientFundamentalData("DCF requires a current or diluted share count")
        bridge = ltm.equity_bridge
        dcf = discounted_cash_flow(
            DCFInputs(
                projected_free_cash_flows=projection.free_cash_flows,
                discount_rate=capital_cost.wacc,
                terminal_growth_rate=terminal_growth,
                net_debt=bridge.net_debt_equivalent,
                diluted_shares=shares,
                terminal_cash_flow=projection.terminal_cash_flow(terminal_growth),
            )
        )
        sensitivity = operating_sensitivity_matrix(
            projection,
            _sensitivity_axis(capital_cost.wacc, 0.01, 2),
            _sensitivity_axis(terminal_growth, 0.005, 2, floor=0.0),
            bridge.net_debt_equivalent,
            shares,
            capital_cost.risk_free_rate,
        )
        conservative_value = _conservative_sensitivity_value(
            sensitivity,
            capital_cost.wacc,
            terminal_growth,
        )

        quality_score = _quality_score(
            current_roic,
            capital_cost.wacc,
            revenue_growth,
            operating_margin,
            capital_cost.debt_and_leases,
            ltm.fcff(capital_cost.marginal_tax_rate),
        )
        valuation_gap = (dcf.value_per_share - snapshot.latest_price) / max(
            snapshot.latest_price, 1e-12
        )
        dcf_margin_of_safety = (
            dcf.value_per_share - snapshot.latest_price
        ) / dcf.value_per_share
        entry_price_ceiling = dcf.value_per_share * (1 - self._entry_buffer)
        entry_buffer_passed = snapshot.latest_price <= entry_price_ceiling
        score = _clamp(0.70 * tanh(valuation_gap / 0.30) + 0.30 * quality_score)
        if not entry_buffer_passed:
            score = min(score, 0.0)
        risks = _model_risks(
            ltm,
            dcf.terminal_value_share,
            revenue_growth,
            projection.years,
        )
        if conservative_value < snapshot.latest_price:
            risks += (
                "Fair value falls below market price when WACC rises 1% and terminal "
                + "growth falls 0.5%; the base recommendation is sensitivity-dependent",
            )
        if not entry_buffer_passed:
            risks += (
                (
                    f"DCF fair value does not provide the configured {self._entry_buffer:.1%} "
                    "entry buffer; wait for a lower price or a stronger model revision"
                ),
            )
        confidence = _confidence(ltm, capital_cost.beta_observations, dcf.terminal_value_share)
        evidence = tuple(snapshot.evidence) + (
            EvidenceReference(
                source="market-wacc",
                reference=capital_cost.rate_observation.source_url,
                observed_at=datetime.combine(
                    capital_cost.rate_observation.observed_at,
                    time.min,
                    tzinfo=UTC,
                ),
            ),
            EvidenceReference(
                source="market-credit-spreads",
                reference=capital_cost.credit_spread_source_url,
                observed_at=datetime.combine(
                    capital_cost.credit_spread_observed_at,
                    time.min,
                    tzinfo=UTC,
                ),
            ),
            EvidenceReference(
                source="deterministic-fcff-dcf",
                reference=f"model://fcff-dcf/{snapshot.symbol}/{snapshot.as_of.date().isoformat()}",
                observed_at=snapshot.as_of,
            ),
        )
        finding = AgentFinding(
            agent=self.name,
            subject=snapshot.symbol,
            score=score,
            confidence=confidence,
            thesis=(
                f"FCFF DCF estimates {dcf.value_per_share:.2f} per share versus "
                f"{snapshot.latest_price:.2f}; WACC is {capital_cost.wacc:.2%}, "
                f"terminal growth is {terminal_growth:.2%}, quality is {quality_score:.2f}, "
                f"and the entry ceiling is {entry_price_ceiling:.2f}."
            ),
            evidence=evidence,
            risks=risks,
            invalidation_conditions=(
                "Revenue, margins or reinvestment diverge materially from the modeled convergence",
                "Market beta, ERP, risk-free rate or credit spread changes materially",
                "Enterprise-to-equity claims or nonoperating assets are restated",
            ),
        )
        return FundamentalAnalysis(
            dcf=dcf,
            projected_free_cash_flows=projection.free_cash_flows,
            quality_score=quality_score,
            finding=finding,
            ltm=ltm,
            capital_cost=capital_cost,
            projection=projection,
            sensitivity=sensitivity,
            model_assumptions={
                "cash_flow": "FCFF",
                "discount_rate": "market-value WACC",
                "projection_years": self._projection_years,
                "initial_revenue_growth": revenue_growth,
                "stable_ebit_margin": stable_margin,
                "current_roic": current_roic,
                "stable_roic": stable_roic,
                "terminal_growth_rate": terminal_growth,
                "terminal_reinvestment_rate": terminal_growth / stable_roic,
                "entry_buffer": self._entry_buffer,
                "entry_price_ceiling": entry_price_ceiling,
                "dcf_margin_of_safety": dcf_margin_of_safety,
                "entry_buffer_passed": entry_buffer_passed,
                "conservative_sensitivity_value": conservative_value,
                "conservative_sensitivity_gap": (
                    conservative_value / snapshot.latest_price - 1
                ),
                "enterprise_to_equity_adjustment": bridge.enterprise_to_equity_adjustment,
                "lease_interest_reclassification": capital_cost.lease_interest_adjustment,
            },
        )


def _validate_company_for_fcff(ltm) -> None:
    try:
        sic = int(ltm.industry_code) if ltm.industry_code is not None else None
    except ValueError:
        sic = None
    if sic is not None and 6000 <= sic <= 6799:
        raise UnsupportedFundamentalModel(
            "FCFF/WACC DCF is not appropriate for financial institutions; "
            "use dividend discount or residual-income valuation"
        )
    if ltm.revenue is None or ltm.revenue <= 0 or ltm.ebit is None:
        raise InsufficientFundamentalData("FCFF DCF requires positive revenue and reported EBIT")
    if ltm.ebit <= 0:
        raise UnsupportedFundamentalModel(
            "Negative EBIT indicates an early or distressed life-cycle stage; "
            "use probability-weighted revenue, margin and survival scenarios"
        )


def _historical_revenue_growth(snapshot: AssetDataSnapshot) -> float:
    eligible = sorted(
        (
            item
            for item in snapshot.fundamentals
            if item.provenance.available_at <= snapshot.as_of
            and item.revenue is not None
            and item.revenue > 0
        ),
        key=lambda item: item.period_end,
        reverse=True,
    )
    if not eligible:
        raise InsufficientFundamentalData("revenue growth requires reported revenue")
    latest = eligible[0]
    if latest.filing_type.upper() == "10-Q":
        if latest.period_start is None:
            raise InsufficientFundamentalData("YTD growth requires XBRL period_start")
        current_days = (latest.period_end - latest.period_start).days
        comparables = []
        for item in eligible[1:]:
            if item.filing_type.upper() != "10-Q" or item.period_start is None:
                continue
            year_gap = (latest.period_end - item.period_end).days
            duration_gap = abs((item.period_end - item.period_start).days - current_days)
            if 330 <= year_gap <= 400 and duration_gap <= 21:
                comparables.append((duration_gap, abs(year_gap - 365), item))
        if comparables:
            prior = min(comparables, key=lambda value: value[:2])[2]
            return latest.revenue / prior.revenue - 1

    annual = [item for item in eligible if item.filing_type.upper() == "10-K"]
    if len(annual) < 2:
        raise InsufficientFundamentalData(
            "revenue growth requires comparable YTD periods or two annual filings"
        )
    return annual[0].revenue / annual[1].revenue - 1


def _stable_operating_margin(snapshot: AssetDataSnapshot, current_margin: float) -> float:
    margins = [
        item.ebit / item.revenue
        for item in snapshot.fundamentals
        if item.ebit is not None and item.revenue is not None and item.revenue > 0
    ]
    normalized = median(margins) if margins else current_margin
    return normalized if normalized > 0 else current_margin


def _invested_capital(ltm) -> float:
    if ltm.total_equity is None:
        raise InsufficientFundamentalData("ROIC requires reported total equity")
    capital = (
        ltm.total_equity
        + (ltm.total_debt or 0.0)
        + (ltm.operating_lease_liabilities or 0.0)
        - (ltm.cash_and_equivalents or 0.0)
        - (ltm.short_term_investments or 0.0)
        - (ltm.long_term_investments or 0.0)
    )
    if capital <= 0:
        raise UnsupportedFundamentalModel(
            "reported invested capital is non-positive; ROIC-based convergence is unreliable"
        )
    return capital


def _quality_score(
    roic: float,
    wacc: float,
    revenue_growth: float,
    operating_margin: float,
    debt: float,
    fcff: float | None,
) -> float:
    components = [
        _clamp((roic - wacc) / 0.10),
        _clamp(revenue_growth / 0.15),
        _clamp((operating_margin - 0.10) / 0.20),
    ]
    if fcff is not None and fcff > 0:
        components.append(_clamp((3.0 - debt / fcff) / 3.0))
    return mean(components)


def _model_risks(ltm, terminal_share, revenue_growth, years) -> tuple[str, ...]:
    risks = []
    if terminal_share > 0.75:
        risks.append("More than 75% of enterprise value comes from terminal value")
    if abs(revenue_growth) > 0.50:
        risks.append(
            "Observed revenue growth exceeds 50%; the model preserves it initially and "
            f"forces convergence over {len(years)} years"
        )
    if ltm.levered_free_cash_flow is not None and ltm.levered_free_cash_flow <= 0:
        risks.append("Observed LTM cash conversion is negative despite positive operating profit")
    missing_bridge = [
        name
        for name in ("total_debt", "cash_and_equivalents", "current_shares_outstanding")
        if getattr(ltm, name) is None
    ]
    if missing_bridge:
        risks.append("Equity bridge has unreported fields: " + ", ".join(missing_bridge))
    unreported_adjustments = [
        name
        for name in (
            "short_term_investments",
            "long_term_investments",
            "operating_lease_liabilities",
            "preferred_stock",
            "noncontrolling_interest",
            "pension_liabilities",
        )
        if getattr(ltm, name) is None
    ]
    if unreported_adjustments:
        risks.append(
            "Unreported equity-bridge adjustments are treated as zero: "
            + ", ".join(unreported_adjustments)
        )
    return tuple(risks)


def _confidence(ltm, beta_observations: int, terminal_share: float) -> float:
    required = (
        ltm.revenue,
        ltm.ebit,
        ltm.total_equity,
        ltm.total_debt,
        ltm.cash_and_equivalents,
        ltm.share_count,
    )
    completeness = sum(value is not None for value in required) / len(required)
    confidence = 0.45 + 0.35 * completeness + min(beta_observations / 60, 1) * 0.10
    if terminal_share > 0.75:
        confidence -= min((terminal_share - 0.75) * 0.60, 0.20)
    return max(0.20, min(confidence, 0.90))


def _sensitivity_axis(
    center: float,
    step: float,
    radius: int,
    floor: float = 0.0001,
) -> tuple[float, ...]:
    return tuple(max(floor, center + offset * step) for offset in range(-radius, radius + 1))


def _conservative_sensitivity_value(sensitivity, wacc, growth) -> float:
    wacc_key = min(sensitivity, key=lambda value: abs(value - (wacc + 0.01)))
    growth_values = sensitivity[wacc_key]
    growth_key = min(growth_values, key=lambda value: abs(value - (growth - 0.005)))
    value = growth_values[growth_key]
    if value is None:
        raise ValueError("conservative WACC/g sensitivity cell is not economically valid")
    return value


def _clamp(value: float) -> float:
    return max(-1.0, min(float(value), 1.0))
