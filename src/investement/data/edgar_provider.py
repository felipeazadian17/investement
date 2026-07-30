import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import isnan
from pathlib import Path
from typing import Any

from investement.data.normalize import normalize_symbol
from investement.domain import DataProvenance, FundamentalSnapshot


@dataclass(frozen=True)
class FilingRecord:
    symbol: str
    form: str
    filing_date: date
    accepted_at: datetime
    accession_number: str | None
    primary_document: str | None
    provenance: DataProvenance


class EdgarProvider:
    """Read-only EdgarTools adapter with explicit SEC identity and filing dates."""

    name = "sec-edgar"

    def __init__(
        self,
        identity: str,
        company_factory: Callable[[str], Any] | None = None,
        identity_setter: Callable[[str], None] | None = None,
        data_directory: Path | None = None,
        cache_directory: Path | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if "@" not in identity or len(identity.strip()) < 5:
            raise ValueError("SEC identity should contain a name and contact email")
        self._identity = identity.strip()
        self._company_factory = company_factory
        self._identity_setter = identity_setter
        self._data_directory = Path(data_directory).resolve() if data_directory else None
        self._cache_directory = Path(cache_directory).resolve() if cache_directory else None
        self._clock = clock

    def _bindings(self) -> tuple:
        if self._company_factory is not None:
            return self._company_factory, self._identity_setter
        if self._data_directory is not None:
            self._data_directory.mkdir(parents=True, exist_ok=True)
            os.environ["EDGAR_LOCAL_DATA_DIR"] = str(self._data_directory)
        if self._cache_directory is not None:
            self._cache_directory.mkdir(parents=True, exist_ok=True)
            os.environ["EDGAR_CACHE_DIR"] = str(self._cache_directory)
        try:
            from edgar import Company, set_identity
        except ImportError as exc:
            raise RuntimeError(
                "edgartools is optional; install with `pip install -e '.[data]'`"
            ) from exc
        return Company, set_identity

    def latest_filings(
        self,
        symbol: str,
        forms: Sequence[str] = ("10-K", "10-Q", "8-K"),
        limit: int = 10,
        filed_after: date | None = None,
        available_before: datetime | None = None,
    ) -> Sequence[FilingRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        cleaned_forms = tuple(form.strip().upper() for form in forms if form.strip())
        if not cleaned_forms:
            raise ValueError("at least one filing form is required")

        company_factory, identity_setter = self._bindings()
        if identity_setter is not None:
            identity_setter(self._identity)
        normalized = normalize_symbol(symbol)
        company = company_factory(normalized)
        filings = company.get_filings(
            form=list(cleaned_forms),
            filing_date=_filing_date_range(filed_after, available_before),
            amendments=False,
        )
        retrieved_at = self._clock()
        records = []
        for filing in filings:
            filing_date = _as_date(filing.filing_date)
            accepted_at = _accepted_at(filing)
            if available_before is not None and accepted_at > available_before:
                continue
            accession = getattr(filing, "accession_number", None)
            primary_document = getattr(filing, "primary_document", None)
            records.append(
                FilingRecord(
                    symbol=normalized,
                    form=str(filing.form),
                    filing_date=filing_date,
                    accepted_at=accepted_at,
                    accession_number=str(accession) if accession is not None else None,
                    primary_document=(
                        str(primary_document) if primary_document is not None else None
                    ),
                    provenance=DataProvenance(
                        source=self.name,
                        retrieved_at=retrieved_at,
                        available_at=accepted_at,
                        raw_reference=_filing_url(filing),
                        metadata={"company_cik": getattr(company, "cik", None)},
                    ),
                )
            )
            if len(records) == limit:
                break
        return records

    def filing_text(self, symbol: str, form: str = "10-K") -> str:
        company_factory, identity_setter = self._bindings()
        if identity_setter is not None:
            identity_setter(self._identity)
        filing = (
            company_factory(normalize_symbol(symbol))
            .get_filings(form=form.upper(), amendments=False)
            .latest()
        )
        return str(filing.text())

    def latest_fundamentals(
        self,
        symbol: str,
        forms: Sequence[str] = ("10-K", "10-Q"),
        limit: int = 8,
        filed_after: date | None = None,
        available_before: datetime | None = None,
    ) -> Sequence[FundamentalSnapshot]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        cleaned_forms = tuple(
            form.strip().upper() for form in forms if form.strip().upper() in ("10-K", "10-Q")
        )
        if not cleaned_forms:
            raise ValueError("XBRL fundamentals require at least one 10-K or 10-Q form")

        company_factory, identity_setter = self._bindings()
        if identity_setter is not None:
            identity_setter(self._identity)
        normalized = normalize_symbol(symbol)
        company = company_factory(normalized)
        filings = company.get_filings(
            form=list(cleaned_forms),
            filing_date=_filing_date_range(filed_after, available_before),
            amendments=False,
        )
        retrieved_at = self._clock()
        snapshots = []
        for filing in filings:
            accepted_at = _accepted_at(filing)
            if available_before is not None and accepted_at > available_before:
                continue
            snapshots.append(
                _extract_fundamental_snapshot(
                    normalized,
                    filing,
                    retrieved_at,
                    company_cik=getattr(company, "cik", None),
                    company_sic=getattr(company, "sic", None),
                )
            )
            if len(snapshots) == limit:
                break
        return snapshots


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _accepted_at(filing: Any) -> datetime:
    value = getattr(filing, "acceptance_datetime", None)
    if value is None:
        raise ValueError("SEC filing is missing acceptance_datetime")
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _filing_date_range(
    filed_after: date | None,
    available_before: datetime | None,
) -> str | None:
    if filed_after is None and available_before is None:
        return None
    start = filed_after.isoformat() if filed_after is not None else ""
    end = available_before.date().isoformat() if available_before is not None else ""
    return f"{start}:{end}"


def _filing_url(filing: Any) -> str | None:
    for name in ("homepage_url", "filing_url"):
        value = getattr(filing, name, None)
        if value:
            return str(value)
    return None


_CONCEPTS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ),
    "ebit": ("OperatingIncomeLoss",),
    "net_income": (
        "NetIncomeLoss",
        "ProfitLoss",
    ),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "income_tax_expense": ("IncomeTaxExpenseBenefit",),
    "interest_expense": (
        "InterestExpenseNonOperating",
        "InterestAndDebtExpense",
        "InterestExpense",
    ),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capital_expenditure": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "depreciation_and_amortization": (
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    ),
    "stock_based_compensation": (
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
    ),
    "cash_and_equivalents": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "debt_current": (
        "LongTermDebtCurrent",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "ShortTermBorrowings",
    ),
    "debt_noncurrent": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    ),
    "debt_total": (
        "LongTermDebtAndFinanceLeaseObligations",
        "LongTermDebt",
    ),
    "short_term_investments": (
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ),
    "long_term_investments": (
        "LongTermInvestments",
        "MarketableSecuritiesNoncurrent",
    ),
    "operating_lease_current": ("OperatingLeaseLiabilityCurrent",),
    "operating_lease_noncurrent": ("OperatingLeaseLiabilityNoncurrent",),
    "operating_lease_total": ("OperatingLeaseLiability",),
    "preferred_stock": (
        "PreferredStocksIncludingAdditionalPaidInCapital",
        "PreferredStockValue",
    ),
    "noncontrolling_interest": (
        "MinorityInterest",
        "NoncontrollingInterestInConsolidatedEntity",
    ),
    "pension_liabilities": (
        "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent",
        "DefinedBenefitPensionPlanLiabilitiesNoncurrent",
    ),
    "total_equity": (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
    "total_assets": ("Assets",),
    "current_shares_outstanding": (
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
    ),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}


def _extract_fundamental_snapshot(
    symbol: str,
    filing: Any,
    retrieved_at: datetime,
    company_cik: Any = None,
    company_sic: Any = None,
) -> FundamentalSnapshot:
    accepted_at = _accepted_at(filing)
    report_end = _as_date(
        getattr(filing, "period_of_report", None) or filing.filing_date
    )
    form = str(filing.form).upper()
    period_basis = "fiscal-ytd" if form == "10-Q" else "fiscal-year"
    xbrl = filing.xbrl()
    income = xbrl.statements.income_statement().to_dataframe()
    balance = xbrl.statements.balance_sheet().to_dataframe()
    cash_flow = xbrl.statements.cash_flow_statement().to_dataframe()

    duration_column = _statement_period_column(income, report_end, period_basis)
    cash_flow_column = _statement_period_column(cash_flow, report_end, period_basis)
    instant_column = _statement_period_column(balance, report_end, "instant")
    selected = {}

    revenue, selected["revenue"] = _statement_value(
        income, _CONCEPTS["revenue"], duration_column
    )
    ebit, selected["ebit"] = _statement_value(income, _CONCEPTS["ebit"], duration_column)
    duration_values = {}
    for name in (
        "net_income",
        "pretax_income",
        "income_tax_expense",
        "interest_expense",
    ):
        duration_values[name], selected[name] = _statement_value(
            income, _CONCEPTS[name], duration_column
        )
    operating_cash_flow, selected["operating_cash_flow"] = _statement_value(
        cash_flow, _CONCEPTS["operating_cash_flow"], cash_flow_column
    )
    capital_expenditure, selected["capital_expenditure"] = _statement_value(
        cash_flow, _CONCEPTS["capital_expenditure"], cash_flow_column
    )
    for name in ("depreciation_and_amortization", "stock_based_compensation"):
        duration_values[name], selected[name] = _statement_value(
            cash_flow, _CONCEPTS[name], cash_flow_column
        )
    cash, selected["cash_and_equivalents"] = _statement_value(
        balance, _CONCEPTS["cash_and_equivalents"], instant_column
    )
    current_debt, current_concept = _statement_value(
        balance, _CONCEPTS["debt_current"], instant_column
    )
    noncurrent_debt, noncurrent_concept = _statement_value(
        balance, _CONCEPTS["debt_noncurrent"], instant_column
    )
    if current_debt is not None or noncurrent_debt is not None:
        total_debt = (current_debt or 0.0) + (noncurrent_debt or 0.0)
        selected["total_debt"] = "+".join(
            concept for concept in (current_concept, noncurrent_concept) if concept
        )
    else:
        total_debt, selected["total_debt"] = _statement_value(
            balance, _CONCEPTS["debt_total"], instant_column
        )
    diluted_shares, selected["diluted_shares"] = _statement_value(
        income, _CONCEPTS["diluted_shares"], duration_column
    )
    instant_values = {}
    for name in (
        "short_term_investments",
        "long_term_investments",
        "preferred_stock",
        "noncontrolling_interest",
        "pension_liabilities",
        "total_equity",
        "total_assets",
        "current_shares_outstanding",
    ):
        instant_values[name], selected[name] = _statement_value(
            balance, _CONCEPTS[name], instant_column
        )
        if instant_values[name] is None:
            instant_values[name], selected[name] = _instant_fact_value(
                xbrl,
                _CONCEPTS[name],
                report_end,
                accepted_at.date() if name == "current_shares_outstanding" else report_end,
            )
    operating_lease, selected["operating_lease_liabilities"] = _combined_value(
        balance,
        instant_column,
        _CONCEPTS["operating_lease_current"],
        _CONCEPTS["operating_lease_noncurrent"],
        _CONCEPTS["operating_lease_total"],
    )

    period_start = _column_period_start(xbrl, duration_column, report_end)
    accession = getattr(filing, "accession_number", None)
    return FundamentalSnapshot(
        symbol=symbol,
        period_end=report_end,
        filing_type=form,
        currency=_reporting_currency(xbrl),
        revenue=revenue,
        ebit=ebit,
        operating_cash_flow=operating_cash_flow,
        capital_expenditure=(abs(capital_expenditure) if capital_expenditure is not None else None),
        cash_and_equivalents=cash,
        total_debt=total_debt,
        diluted_shares=diluted_shares,
        provenance=DataProvenance(
            source="sec-edgar-xbrl",
            retrieved_at=retrieved_at,
            available_at=accepted_at,
            raw_reference=_filing_url(filing),
            adjustments=("consolidated-facts-only", "capex-as-positive-outflow"),
            metadata={
                "accession_number": str(accession) if accession is not None else None,
                "company_cik": company_cik,
                "company_sic": company_sic,
                "period_basis": period_basis,
                "xbrl_concepts": selected,
            },
        ),
        period_start=period_start,
        period_basis=period_basis,
        **duration_values,
        **instant_values,
        operating_lease_liabilities=operating_lease,
    )


def _statement_period_column(frame: Any, report_end: date, basis: str) -> Any:
    prefix = report_end.isoformat()
    candidates = [column for column in frame.columns if str(column).startswith(prefix)]
    if not candidates:
        raise ValueError(f"XBRL statement has no column for report period {prefix}")
    if basis == "fiscal-ytd":
        ytd = [column for column in candidates if "YTD" in str(column).upper()]
        if ytd:
            return ytd[0]
    if basis == "fiscal-year":
        annual = [column for column in candidates if "FY" in str(column).upper()]
        if annual:
            return annual[0]
        non_quarter = [
            column
            for column in candidates
            if "Q1" not in str(column).upper()
            and "Q2" not in str(column).upper()
            and "Q3" not in str(column).upper()
        ]
        if non_quarter:
            return non_quarter[0]
    return candidates[0]


def _statement_value(frame: Any, concepts: Sequence[str], column: Any) -> tuple[float | None, str]:
    if "concept" not in frame.columns or column not in frame.columns:
        return None, ""
    normalized_candidates = {_normalize_concept(concept) for concept in concepts}
    rows = frame[
        frame["concept"].map(lambda value: _normalize_concept(str(value))).isin(
            normalized_candidates
        )
    ]
    if rows.empty and "standard_concept" in frame.columns:
        rows = frame[
            frame["standard_concept"].map(lambda value: _normalize_concept(str(value))).isin(
                normalized_candidates
            )
        ]
    if rows.empty:
        return None, ""
    for dimension_column in ("dimension_label", "dimension_axis", "dimension"):
        if dimension_column in rows.columns:
            consolidated = rows[rows[dimension_column].isna()]
            if not consolidated.empty:
                rows = consolidated
    for _, row in rows.iterrows():
        value = row[column]
        if value is None or _is_nan(value):
            continue
        return float(value), str(row["concept"])
    return None, ""


def _combined_value(
    frame: Any,
    column: Any,
    current_concepts: Sequence[str],
    noncurrent_concepts: Sequence[str],
    total_concepts: Sequence[str],
) -> tuple[float | None, str]:
    current, current_concept = _statement_value(frame, current_concepts, column)
    noncurrent, noncurrent_concept = _statement_value(frame, noncurrent_concepts, column)
    if current is not None or noncurrent is not None:
        concepts = "+".join(
            item for item in (current_concept, noncurrent_concept) if item
        )
        return (current or 0.0) + (noncurrent or 0.0), concepts
    return _statement_value(frame, total_concepts, column)


def _instant_fact_value(
    xbrl: Any,
    concepts: Sequence[str],
    minimum_date: date,
    maximum_date: date,
) -> tuple[float | None, str]:
    candidates = []
    for concept in concepts:
        prefixes = ("dei_", "dei:") if concept.startswith("Entity") else ("us-gaap_", "us-gaap:")
        for qualified in (concept, *(prefix + concept for prefix in prefixes)):
            try:
                frame = xbrl.facts.query().by_concept(qualified, exact=True).to_dataframe()
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            if frame.empty:
                continue
            for _, row in frame.iterrows():
                if bool(row.get("is_dimensioned", False)):
                    continue
                instant = row.get("period_instant")
                if instant is None or _is_nan(instant):
                    continue
                try:
                    instant_date = _as_date(instant)
                except (TypeError, ValueError):
                    continue
                if not minimum_date <= instant_date <= maximum_date:
                    continue
                value = row.get("numeric_value", row.get("value"))
                if value is None or _is_nan(value):
                    continue
                candidates.append((instant_date, float(value), str(row.get("concept", qualified))))
    if not candidates:
        return None, ""
    _, value, selected = max(candidates, key=lambda item: item[0])
    return value, selected


def _normalize_concept(value: str) -> str:
    return value.replace("us-gaap:", "").replace("us-gaap_", "").replace(":", "_").lower()


def _is_nan(value: Any) -> bool:
    try:
        return isnan(float(value))
    except (TypeError, ValueError):
        return False


def _reporting_currency(xbrl: Any) -> str:
    for concept in ("dei_EntityReportingCurrencyISOCode", "dei_DocumentCurrency"):
        try:
            frame = xbrl.facts.query().by_concept(concept, exact=True).to_dataframe(
                "value"
            )
            if not frame.empty:
                value = str(frame.iloc[0]["value"]).strip().upper()
                if len(value) == 3 and value.isalpha():
                    return value
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return "USD"


def _column_period_start(xbrl: Any, column: Any, report_end: date) -> date | None:
    try:
        frame = xbrl.facts.query().to_dataframe(
            "period_start", "period_end", "period_type", "is_dimensioned"
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    if frame.empty or "period_start" not in frame.columns:
        return None
    candidates = []
    for _, row in frame.iterrows():
        if str(row.get("period_type", "")) != "duration":
            continue
        try:
            period_end = _as_date(row["period_end"])
            period_start = _as_date(row["period_start"])
        except (KeyError, TypeError, ValueError):
            continue
        duration_days = (report_end - period_start).days
        if period_end == report_end and 30 <= duration_days <= 400:
            candidates.append(period_start)
    return min(candidates) if candidates else None
