import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from itertools import pairwise
from math import isfinite
from statistics import mean
from typing import Protocol
from urllib.request import Request, urlopen

from investement.data.protocols import MarketDataProvider
from investement.domain import PriceBar
from investement.valuation.fundamentals import LTMFundamentals

DAMODARAN_MARKET_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm"
DAMODARAN_RATINGS_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html"


@dataclass(frozen=True)
class MarketRateObservation:
    observed_at: date
    risk_free_rate: float
    equity_risk_premium: float
    source_url: str

    def __post_init__(self) -> None:
        if not 0 < self.risk_free_rate < 1:
            raise ValueError("risk-free rate must be between zero and one")
        if not 0 < self.equity_risk_premium < 1:
            raise ValueError("equity risk premium must be between zero and one")


class MarketRateProvider(Protocol):
    def rates(self, as_of: datetime) -> MarketRateObservation: ...


@dataclass(frozen=True)
class CreditSpreadObservation:
    observed_at: date
    thresholds: tuple[tuple[float, float], ...]
    source_url: str

    def __post_init__(self) -> None:
        if not self.thresholds:
            raise ValueError("credit-spread table cannot be empty")
        if any(spread < 0 or not isfinite(spread) for _, spread in self.thresholds):
            raise ValueError("credit spreads must be finite and non-negative")

    def spread(self, interest_coverage: float) -> float:
        return next(
            spread
            for ceiling, spread in self.thresholds
            if interest_coverage <= ceiling
        )


class CreditSpreadProvider(Protocol):
    def spreads(self, as_of: datetime) -> CreditSpreadObservation: ...


class FixedMarketRateProvider:
    """Deterministic fixture/configuration provider; production should use dated market data."""

    def __init__(self, observation: MarketRateObservation) -> None:
        self._observation = observation

    def rates(self, as_of: datetime) -> MarketRateObservation:
        if self._observation.observed_at > as_of.date():
            raise ValueError("market-rate observation was unavailable at as_of")
        return self._observation


class FixedCreditSpreadProvider:
    def __init__(self, observation: CreditSpreadObservation) -> None:
        self._observation = observation

    def spreads(self, as_of: datetime) -> CreditSpreadObservation:
        if self._observation.observed_at > as_of.date():
            raise ValueError("credit-spread observation was unavailable at as_of")
        return self._observation


class DamodaranMarketRateProvider:
    def __init__(
        self,
        loader: Callable[[str], str] | None = None,
    ) -> None:
        self._loader = loader or _download_text
        self._cache: MarketRateObservation | None = None

    def rates(self, as_of: datetime) -> MarketRateObservation:
        observation = self._cache or self._parse(self._loader(DAMODARAN_MARKET_URL))
        self._cache = observation
        if observation.observed_at > as_of.date():
            raise ValueError(
                "latest Damodaran market-rate observation is newer than as_of; "
                "a historical point-in-time provider is required"
            )
        return observation

    @staticmethod
    def _parse(document: str) -> MarketRateObservation:
        text = re.sub(r"<[^>]+>", " ", unescape(document))
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"(\d+\.)\s+(\d+%)", r"\1\2", text)
        date_match = re.search(
            r"Implied ERP on ([A-Za-z]+) (\d{1,2}), (\d{4})\s*=\s*([0-9.]+)%",
            text,
            re.IGNORECASE,
        )
        risk_free_match = re.search(
            r"US treasury rate of\s*([0-9.]+)%\s*used as the riskfree rate",
            text,
            re.IGNORECASE,
        )
        if date_match is None or risk_free_match is None:
            raise ValueError("could not parse dated ERP and risk-free rate from Damodaran")
        observed_at = datetime.strptime(
            " ".join(date_match.group(index) for index in (1, 2, 3)),
            "%B %d %Y",
        ).replace(tzinfo=UTC).date()
        return MarketRateObservation(
            observed_at=observed_at,
            risk_free_rate=float(risk_free_match.group(1)) / 100,
            equity_risk_premium=float(date_match.group(4)) / 100,
            source_url=DAMODARAN_MARKET_URL,
        )


class DamodaranCreditSpreadProvider:
    def __init__(self, loader: Callable[[str], str] | None = None) -> None:
        self._loader = loader or _download_text
        self._cache: CreditSpreadObservation | None = None

    def spreads(self, as_of: datetime) -> CreditSpreadObservation:
        observation = self._cache or self._parse(self._loader(DAMODARAN_RATINGS_URL))
        self._cache = observation
        if observation.observed_at > as_of.date():
            raise ValueError("credit-spread observation was unavailable at as_of")
        return observation

    @staticmethod
    def _parse(document: str) -> CreditSpreadObservation:
        date_match = re.search(
            r"Data used is as of\s+([A-Za-z]+)\s+(\d{4})",
            re.sub(r"<[^>]+>", " ", unescape(document)),
            re.IGNORECASE,
        )
        if date_match is None:
            raise ValueError("could not parse date from Damodaran credit-spread table")
        observed_at = datetime.strptime(
            f"{date_match.group(1)} 1 {date_match.group(2)}",
            "%B %d %Y",
        ).replace(tzinfo=UTC).date()
        parser = _TableParser()
        parser.feed(document)
        thresholds = []
        for row in parser.rows:
            if len(row) < 4:
                continue
            try:
                ceiling = float(row[1].replace(",", ""))
                spread = float(row[3].replace("%", "")) / 100
            except ValueError:
                continue
            thresholds.append((ceiling, spread))
        if len(thresholds) < 10:
            raise ValueError("Damodaran credit-spread table is incomplete")
        thresholds.sort(key=lambda item: item[0])
        thresholds[-1] = (float("inf"), thresholds[-1][1])
        return CreditSpreadObservation(
            observed_at=observed_at,
            thresholds=tuple(thresholds),
            source_url=DAMODARAN_RATINGS_URL,
        )


@dataclass(frozen=True)
class CapitalCostResult:
    risk_free_rate: float
    equity_risk_premium: float
    raw_beta: float
    adjusted_beta: float
    cost_of_equity: float
    pretax_cost_of_debt: float
    after_tax_cost_of_debt: float
    marginal_tax_rate: float
    market_equity: float
    debt_and_leases: float
    equity_weight: float
    debt_weight: float
    wacc: float
    interest_coverage: float | None
    default_spread: float
    lease_interest_adjustment: float
    rate_observation: MarketRateObservation
    beta_observations: int
    credit_spread_observed_at: date
    credit_spread_source_url: str


class MarketWACCBuilder:
    def __init__(
        self,
        market_data: MarketDataProvider,
        rate_provider: MarketRateProvider | None = None,
        benchmark_symbol: str = "SPY",
        beta_lookback_years: int = 5,
        minimum_beta_observations: int = 24,
        credit_spread_provider: CreditSpreadProvider | None = None,
    ) -> None:
        self._market_data = market_data
        self._rate_provider = rate_provider or DamodaranMarketRateProvider()
        self._benchmark_symbol = benchmark_symbol
        self._beta_lookback_years = beta_lookback_years
        self._minimum_beta_observations = minimum_beta_observations
        self._credit_spread_provider = (
            credit_spread_provider or DamodaranCreditSpreadProvider()
        )

    def build(
        self,
        symbol: str,
        as_of: datetime,
        latest_price: float,
        fundamentals: LTMFundamentals,
    ) -> CapitalCostResult:
        rates = self._rate_provider.rates(as_of)
        credit_spreads = self._credit_spread_provider.spreads(as_of)
        start = as_of.date() - timedelta(days=366 * self._beta_lookback_years)
        company_bars = self._market_data.history(symbol, start, as_of.date(), "1d")
        benchmark_bars = self._market_data.history(
            self._benchmark_symbol,
            start,
            as_of.date(),
            "1d",
        )
        raw_beta, observations = market_beta(
            company_bars,
            benchmark_bars,
            as_of,
            self._minimum_beta_observations,
        )
        adjusted_beta = 0.67 * raw_beta + 0.33
        cost_of_equity = rates.risk_free_rate + adjusted_beta * rates.equity_risk_premium

        debt = max(fundamentals.total_debt or 0.0, 0.0)
        leases = max(fundamentals.operating_lease_liabilities or 0.0, 0.0)
        debt_and_leases = debt + leases
        interest_coverage = _interest_coverage(
            fundamentals,
            debt,
            leases,
            rates.risk_free_rate,
            credit_spreads,
        )
        default_spread = _credit_spread(
            interest_coverage,
            debt_and_leases,
            credit_spreads,
        )
        pretax_cost_of_debt = rates.risk_free_rate + default_spread
        lease_interest_adjustment = leases * pretax_cost_of_debt
        marginal_tax_rate = normalized_marginal_tax_rate(fundamentals.effective_tax_rate)
        after_tax_cost_of_debt = pretax_cost_of_debt * (1 - marginal_tax_rate)

        shares = fundamentals.share_count
        if shares is None:
            raise ValueError("WACC requires a current or diluted share count")
        market_equity = latest_price * shares
        total_capital = market_equity + debt_and_leases
        if total_capital <= 0:
            raise ValueError("WACC requires positive market capital")
        equity_weight = market_equity / total_capital
        debt_weight = debt_and_leases / total_capital
        wacc = equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt
        if not 0 < wacc < 1:
            raise ValueError("calculated WACC is not economically valid")
        return CapitalCostResult(
            risk_free_rate=rates.risk_free_rate,
            equity_risk_premium=rates.equity_risk_premium,
            raw_beta=raw_beta,
            adjusted_beta=adjusted_beta,
            cost_of_equity=cost_of_equity,
            pretax_cost_of_debt=pretax_cost_of_debt,
            after_tax_cost_of_debt=after_tax_cost_of_debt,
            marginal_tax_rate=marginal_tax_rate,
            market_equity=market_equity,
            debt_and_leases=debt_and_leases,
            equity_weight=equity_weight,
            debt_weight=debt_weight,
            wacc=wacc,
            interest_coverage=interest_coverage,
            default_spread=default_spread,
            lease_interest_adjustment=lease_interest_adjustment,
            rate_observation=rates,
            beta_observations=observations,
            credit_spread_observed_at=credit_spreads.observed_at,
            credit_spread_source_url=credit_spreads.source_url,
        )


def market_beta(
    company_bars: Sequence[PriceBar],
    benchmark_bars: Sequence[PriceBar],
    as_of: datetime,
    minimum_observations: int = 24,
) -> tuple[float, int]:
    company_prices = _monthly_prices(company_bars, as_of)
    benchmark_prices = _monthly_prices(benchmark_bars, as_of)
    common_months = sorted(set(company_prices) & set(benchmark_prices))
    company = []
    benchmark = []
    for previous, current in pairwise(common_months):
        company.append(company_prices[current] / company_prices[previous] - 1)
        benchmark.append(benchmark_prices[current] / benchmark_prices[previous] - 1)
    if len(company) < minimum_observations:
        raise ValueError(
            f"beta requires {minimum_observations} monthly observations; found {len(company)}"
        )
    benchmark_mean = mean(benchmark)
    company_mean = mean(company)
    covariance = sum(
        (company_value - company_mean) * (market_value - benchmark_mean)
        for company_value, market_value in zip(company, benchmark)
    )
    variance = sum((value - benchmark_mean) ** 2 for value in benchmark)
    if variance <= 0:
        raise ValueError("benchmark returns have no variance")
    beta = covariance / variance
    if not isfinite(beta):
        raise ValueError("calculated beta is not finite")
    return beta, len(company)


def synthetic_default_spread(
    interest_coverage: float | None,
    debt_and_leases: float,
) -> float:
    if debt_and_leases <= 0:
        return 0.0
    if interest_coverage is None:
        raise ValueError("cost of debt requires interest expense when debt is outstanding")
    thresholds = (
        (0.20, 0.1900),
        (0.65, 0.1600),
        (0.80, 0.1261),
        (1.25, 0.0885),
        (1.50, 0.0509),
        (1.75, 0.0321),
        (2.00, 0.0275),
        (2.25, 0.0184),
        (2.50, 0.0138),
        (3.00, 0.0111),
        (4.25, 0.0089),
        (5.50, 0.0078),
        (6.50, 0.0070),
        (8.50, 0.0055),
        (float("inf"), 0.0040),
    )
    return next(spread for ceiling, spread in thresholds if interest_coverage <= ceiling)


def _credit_spread(
    interest_coverage: float | None,
    debt_and_leases: float,
    observation: CreditSpreadObservation,
) -> float:
    if debt_and_leases <= 0:
        return 0.0
    if interest_coverage is None:
        raise ValueError("cost of debt requires interest coverage")
    return observation.spread(interest_coverage)


def normalized_marginal_tax_rate(effective_rate: float | None) -> float:
    if effective_rate is not None and 0.05 <= effective_rate <= 0.45:
        return effective_rate
    return 0.21


def _interest_coverage(
    fundamentals: LTMFundamentals,
    debt: float,
    leases: float,
    risk_free_rate: float,
    credit_spreads: CreditSpreadObservation,
) -> float | None:
    debt_and_leases = debt + leases
    if debt_and_leases <= 0:
        return None
    if fundamentals.ebit is None:
        return None

    # Solve the synthetic-rating circularity when reported interest is unavailable:
    # spread -> interest expense -> coverage -> spread.
    spread = 0.04
    for _ in range(20):
        cost_of_debt = risk_free_rate + spread
        lease_interest = leases * cost_of_debt
        if fundamentals.interest_expense is not None and fundamentals.interest_expense > 0:
            interest = fundamentals.interest_expense + lease_interest
        else:
            interest = debt_and_leases * cost_of_debt
        adjusted_ebit = fundamentals.ebit + lease_interest
        coverage = adjusted_ebit / interest if interest > 0 else None
        next_spread = _credit_spread(coverage, debt_and_leases, credit_spreads)
        if abs(next_spread - spread) < 1e-8:
            return coverage
        spread = next_spread
    cost_of_debt = risk_free_rate + spread
    lease_interest = leases * cost_of_debt
    interest = fundamentals.interest_expense or debt * cost_of_debt
    return (fundamentals.ebit + lease_interest) / (interest + lease_interest)


def _monthly_prices(bars: Sequence[PriceBar], as_of: datetime) -> dict[tuple[int, int], float]:
    closes = {}
    for bar in sorted(bars, key=lambda item: item.timestamp):
        if bar.timestamp <= as_of and bar.provenance.available_at <= as_of:
            closes[(bar.timestamp.year, bar.timestamp.month)] = float(bar.adjusted_close)
    return closes


def _download_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "investement-research/1.0"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "td" and self._row is not None and self._cell is not None:
            self._row.append(" ".join(self._cell).strip())
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
