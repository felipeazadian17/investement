from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite

from investement.domain import FundamentalSnapshot


class InsufficientFundamentalData(ValueError):
    pass


_DURATION_FIELDS = (
    "revenue",
    "ebit",
    "operating_cash_flow",
    "capital_expenditure",
    "net_income",
    "pretax_income",
    "income_tax_expense",
    "interest_expense",
    "depreciation_and_amortization",
    "stock_based_compensation",
)


@dataclass(frozen=True)
class EquityBridge:
    debt: float
    operating_lease_liabilities: float
    preferred_stock: float
    noncontrolling_interest: float
    pension_liabilities: float
    cash_and_equivalents: float
    short_term_investments: float
    long_term_investments: float

    @property
    def enterprise_to_equity_adjustment(self) -> float:
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
        return nonoperating_assets - claims

    @property
    def net_debt_equivalent(self) -> float:
        return -self.enterprise_to_equity_adjustment


@dataclass(frozen=True)
class LTMFundamentals:
    symbol: str
    period_start: date
    period_end: date
    available_at: datetime
    currency: str
    industry_code: str | None
    revenue: float | None
    ebit: float | None
    operating_cash_flow: float | None
    capital_expenditure: float | None
    net_income: float | None
    pretax_income: float | None
    income_tax_expense: float | None
    interest_expense: float | None
    depreciation_and_amortization: float | None
    stock_based_compensation: float | None
    diluted_shares: float | None
    current_shares_outstanding: float | None
    total_debt: float | None
    cash_and_equivalents: float | None
    short_term_investments: float | None
    long_term_investments: float | None
    operating_lease_liabilities: float | None
    preferred_stock: float | None
    noncontrolling_interest: float | None
    pension_liabilities: float | None
    total_equity: float | None
    total_assets: float | None
    source_filings: tuple[str, ...]

    @property
    def effective_tax_rate(self) -> float | None:
        if self.pretax_income is None or self.income_tax_expense is None:
            return None
        if self.pretax_income <= 0:
            return None
        return self.income_tax_expense / self.pretax_income

    @property
    def levered_free_cash_flow(self) -> float | None:
        if self.operating_cash_flow is None or self.capital_expenditure is None:
            return None
        return self.operating_cash_flow - self.capital_expenditure

    def fcff(self, marginal_tax_rate: float) -> float | None:
        levered = self.levered_free_cash_flow
        if levered is None:
            return None
        if self.interest_expense is None:
            if (self.total_debt or 0.0) > 0:
                return None
            return levered
        return levered + self.interest_expense * (1 - marginal_tax_rate)

    @property
    def share_count(self) -> float | None:
        candidates = tuple(
            value
            for value in (self.current_shares_outstanding, self.diluted_shares)
            if value is not None and value > 0
        )
        return max(candidates) if candidates else None

    @property
    def equity_bridge(self) -> EquityBridge:
        return EquityBridge(
            debt=self.total_debt or 0.0,
            operating_lease_liabilities=self.operating_lease_liabilities or 0.0,
            preferred_stock=self.preferred_stock or 0.0,
            noncontrolling_interest=self.noncontrolling_interest or 0.0,
            pension_liabilities=self.pension_liabilities or 0.0,
            cash_and_equivalents=self.cash_and_equivalents or 0.0,
            short_term_investments=self.short_term_investments or 0.0,
            long_term_investments=self.long_term_investments or 0.0,
        )


def build_ltm_fundamentals(
    snapshots: tuple[FundamentalSnapshot, ...] | list[FundamentalSnapshot],
    as_of: datetime,
) -> LTMFundamentals:
    eligible = [item for item in snapshots if item.provenance.available_at <= as_of]
    if not eligible:
        raise InsufficientFundamentalData("no point-in-time fundamentals are available")
    eligible.sort(key=lambda item: (item.period_end, item.provenance.available_at), reverse=True)
    latest = eligible[0]
    if latest.filing_type.upper() == "10-K":
        return _from_annual(latest)

    annual = next(
        (
            item
            for item in eligible
            if item.filing_type.upper() == "10-K" and item.period_end < latest.period_end
        ),
        None,
    )
    if annual is None:
        raise InsufficientFundamentalData("LTM requires a preceding 10-K")

    current_days = _duration_days(latest)
    prior_ytd = _matching_prior_ytd(eligible, latest, annual, current_days)
    if prior_ytd is None:
        raise InsufficientFundamentalData(
            "LTM requires the comparable prior-year YTD 10-Q; request at least eight filings"
        )
    _require_same_currency(latest, annual, prior_ytd)

    annual_days = _duration_days(annual)
    prior_days = _duration_days(prior_ytd)
    values = {
        field: _ltm_value(annual, latest, prior_ytd, field)
        for field in _DURATION_FIELDS
    }
    diluted_shares = _ltm_weighted_shares(
        annual,
        latest,
        prior_ytd,
        annual_days,
        current_days,
        prior_days,
    )
    ltm_days = annual_days + current_days - prior_days
    return LTMFundamentals(
        symbol=latest.symbol,
        period_start=latest.period_end - timedelta(days=ltm_days - 1),
        period_end=latest.period_end,
        available_at=max(item.provenance.available_at for item in (annual, latest, prior_ytd)),
        currency=latest.currency,
        industry_code=_industry_code(latest),
        diluted_shares=diluted_shares,
        source_filings=tuple(_filing_id(item) for item in (annual, latest, prior_ytd)),
        **values,
        **_instant_values(latest),
    )


def _from_annual(snapshot: FundamentalSnapshot) -> LTMFundamentals:
    period_days = _duration_days(snapshot)
    return LTMFundamentals(
        symbol=snapshot.symbol,
        period_start=snapshot.period_end - timedelta(days=period_days - 1),
        period_end=snapshot.period_end,
        available_at=snapshot.provenance.available_at,
        currency=snapshot.currency,
        industry_code=_industry_code(snapshot),
        diluted_shares=snapshot.diluted_shares,
        source_filings=(_filing_id(snapshot),),
        **{field: getattr(snapshot, field) for field in _DURATION_FIELDS},
        **_instant_values(snapshot),
    )


def _instant_values(snapshot: FundamentalSnapshot) -> dict[str, float | None]:
    return {
        name: getattr(snapshot, name)
        for name in (
            "current_shares_outstanding",
            "total_debt",
            "cash_and_equivalents",
            "short_term_investments",
            "long_term_investments",
            "operating_lease_liabilities",
            "preferred_stock",
            "noncontrolling_interest",
            "pension_liabilities",
            "total_equity",
            "total_assets",
        )
    }


def _ltm_value(
    annual: FundamentalSnapshot,
    current_ytd: FundamentalSnapshot,
    prior_ytd: FundamentalSnapshot,
    field: str,
) -> float | None:
    values = tuple(getattr(item, field) for item in (annual, current_ytd, prior_ytd))
    if any(value is None for value in values):
        return None
    result = float(values[0]) + float(values[1]) - float(values[2])
    if not isfinite(result):
        raise ValueError(f"non-finite LTM {field}")
    return result


def _ltm_weighted_shares(
    annual: FundamentalSnapshot,
    current_ytd: FundamentalSnapshot,
    prior_ytd: FundamentalSnapshot,
    annual_days: int,
    current_days: int,
    prior_days: int,
) -> float | None:
    shares = tuple(item.diluted_shares for item in (annual, current_ytd, prior_ytd))
    if any(value is None for value in shares):
        return None
    denominator = annual_days + current_days - prior_days
    if denominator <= 0:
        raise InsufficientFundamentalData("invalid fiscal periods for LTM share count")
    share_days = (
        float(shares[0]) * annual_days
        + float(shares[1]) * current_days
        - float(shares[2]) * prior_days
    )
    return share_days / denominator


def _matching_prior_ytd(
    snapshots: list[FundamentalSnapshot],
    latest: FundamentalSnapshot,
    annual: FundamentalSnapshot,
    current_days: int,
) -> FundamentalSnapshot | None:
    candidates = []
    for item in snapshots:
        if item.filing_type.upper() != "10-Q" or item.period_end >= annual.period_end:
            continue
        year_gap = (latest.period_end - item.period_end).days
        duration_gap = abs(_duration_days(item) - current_days)
        if 330 <= year_gap <= 400 and duration_gap <= 21:
            candidates.append((duration_gap, abs(year_gap - 365), item))
    return min(candidates, key=lambda value: value[:2])[2] if candidates else None


def _duration_days(snapshot: FundamentalSnapshot) -> int:
    if snapshot.period_start is not None:
        return (snapshot.period_end - snapshot.period_start).days + 1
    if snapshot.filing_type.upper() == "10-K":
        return 365
    raise InsufficientFundamentalData(
        f"{snapshot.symbol} {snapshot.period_end} is missing its XBRL duration start"
    )


def _require_same_currency(*snapshots: FundamentalSnapshot) -> None:
    if len({item.currency for item in snapshots}) != 1:
        raise InsufficientFundamentalData("cannot bridge filings with different currencies")


def _filing_id(snapshot: FundamentalSnapshot) -> str:
    accession = snapshot.provenance.metadata.get("accession_number")
    return str(accession or f"{snapshot.filing_type}:{snapshot.period_end.isoformat()}")


def _industry_code(snapshot: FundamentalSnapshot) -> str | None:
    value = snapshot.provenance.metadata.get("company_sic")
    return str(value) if value is not None else None
