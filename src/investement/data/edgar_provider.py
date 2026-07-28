import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from investement.data.normalize import normalize_symbol
from investement.domain import DataProvenance


@dataclass(frozen=True)
class FilingRecord:
    symbol: str
    form: str
    filing_date: date
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
            filing_date=(filed_after.isoformat() + ":") if filed_after else None,
            amendments=False,
        )
        selected = filings.head(limit) if hasattr(filings, "head") else list(filings)[:limit]
        retrieved_at = self._clock()
        records = []
        for filing in selected:
            filing_date = _as_date(filing.filing_date)
            available_at = datetime.combine(filing_date, time.min, tzinfo=UTC)
            accession = getattr(filing, "accession_number", None)
            primary_document = getattr(filing, "primary_document", None)
            records.append(
                FilingRecord(
                    symbol=normalized,
                    form=str(filing.form),
                    filing_date=filing_date,
                    accession_number=str(accession) if accession is not None else None,
                    primary_document=(
                        str(primary_document) if primary_document is not None else None
                    ),
                    provenance=DataProvenance(
                        source=self.name,
                        retrieved_at=retrieved_at,
                        available_at=min(available_at, retrieved_at),
                        raw_reference=_filing_url(filing),
                        metadata={"company_cik": getattr(company, "cik", None)},
                    ),
                )
            )
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


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _filing_url(filing: Any) -> str | None:
    for name in ("homepage_url", "filing_url"):
        value = getattr(filing, name, None)
        if value:
            return str(value)
    return None
