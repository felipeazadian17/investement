from datetime import UTC, datetime

from investement.agents.models import AssetDataRequest, AssetDataSnapshot
from investement.data import FilingProvider, MarketDataProvider, normalize_symbol
from investement.orchestration import EvidenceReference


class DataAgent:
    name = "data"

    def __init__(
        self,
        market_data: MarketDataProvider,
        filings: FilingProvider | None = None,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._market_data = market_data
        self._filings = filings
        self._clock = clock

    def collect(self, request: AssetDataRequest) -> AssetDataSnapshot:
        symbol = normalize_symbol(request.symbol)
        end = min(request.end, request.as_of.date())
        bars = tuple(
            sorted(
                (
                    bar
                    for bar in self._market_data.history(
                        symbol,
                        request.start,
                        end,
                        request.interval,
                    )
                    if bar.timestamp <= request.as_of
                    and bar.provenance.available_at <= request.as_of
                ),
                key=lambda bar: bar.timestamp,
            )
        )
        if not bars:
            raise ValueError(f"no point-in-time price data available for {symbol}")

        filing_records = ()
        if self._filings is not None and request.filing_limit > 0:
            candidates = self._filings.latest_filings(
                symbol,
                forms=tuple(form.upper() for form in request.filing_forms),
                limit=request.filing_limit,
                filed_after=request.start,
            )
            filing_records = tuple(
                record for record in candidates if _filing_available(record, request.as_of)
            )

        evidence = [_price_evidence(bars[-1])]
        evidence.extend(_filing_evidence(record) for record in filing_records)
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("data agent clock must return a timezone-aware datetime")
        return AssetDataSnapshot(
            symbol=symbol,
            as_of=request.as_of,
            retrieved_at=retrieved_at,
            bars=bars,
            filings=filing_records,
            evidence=tuple(evidence),
        )


def _filing_available(record: object, as_of: datetime) -> bool:
    provenance = getattr(record, "provenance", None)
    available_at = getattr(provenance, "available_at", None)
    if available_at is not None:
        return available_at <= as_of
    filing_date = getattr(record, "filing_date", None)
    return filing_date is None or filing_date <= as_of.date()


def _price_evidence(bar) -> EvidenceReference:
    reference = bar.provenance.raw_reference or f"{bar.symbol}:{bar.timestamp.isoformat()}"
    return EvidenceReference(
        source=bar.provenance.source,
        reference=reference,
        observed_at=bar.provenance.available_at,
    )


def _filing_evidence(record: object) -> EvidenceReference:
    provenance = getattr(record, "provenance", None)
    source = getattr(provenance, "source", "sec-edgar")
    observed_at = getattr(provenance, "available_at", None)
    if observed_at is None:
        filing_date = record.filing_date
        observed_at = datetime.combine(filing_date, datetime.min.time(), tzinfo=UTC)
    reference = (
        getattr(provenance, "raw_reference", None)
        or getattr(record, "homepage_url", None)
        or str(getattr(record, "accession_number", "filing"))
    )
    return EvidenceReference(source=source, reference=reference, observed_at=observed_at)
