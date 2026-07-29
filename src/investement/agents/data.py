from datetime import UTC, datetime

from investement.agents.models import AssetDataRequest, AssetDataSnapshot
from investement.data import (
    FilingProvider,
    FundamentalDataProvider,
    InstrumentDataProvider,
    MarketDataProvider,
    normalize_symbol,
)
from investement.domain import CorporateAction, CorporateActionKind
from investement.orchestration import EvidenceReference


class DataAgent:
    name = "data"

    def __init__(
        self,
        market_data: MarketDataProvider,
        filings: FilingProvider | None = None,
        fundamentals: FundamentalDataProvider | None = None,
        instruments: InstrumentDataProvider | None = None,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._market_data = market_data
        self._filings = filings
        self._fundamentals = fundamentals or (
            filings if filings is not None and hasattr(filings, "latest_fundamentals") else None
        )
        self._instruments = instruments or (
            market_data
            if hasattr(market_data, "fund_snapshot") and hasattr(market_data, "option_chain")
            else None
        )
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
                filed_after=None,
                available_before=request.as_of,
            )
            filing_records = tuple(
                record for record in candidates if _filing_available(record, request.as_of)
            )

        fundamentals = ()
        if (
            self._fundamentals is not None
            and request.include_fundamentals
            and request.filing_limit > 0
        ):
            fundamentals = tuple(
                item
                for item in self._fundamentals.latest_fundamentals(
                    symbol,
                    forms=tuple(form.upper() for form in request.filing_forms),
                    limit=request.filing_limit,
                    filed_after=None,
                    available_before=request.as_of,
                )
                if item.provenance.available_at <= request.as_of
            )

        corporate_actions = _corporate_actions(bars)
        fund = None
        option_chain = None
        if self._instruments is not None and request.include_fund_data:
            fund = self._instruments.fund_snapshot(symbol, request.as_of)
        if self._instruments is not None and request.option_expiration is not None:
            option_chain = self._instruments.option_chain(
                symbol,
                request.option_expiration,
                request.as_of,
            )

        evidence = [_price_evidence(bars[-1])]
        evidence.extend(_filing_evidence(record) for record in filing_records)
        evidence.extend(_fundamental_evidence(item) for item in fundamentals)
        if fund is not None:
            evidence.append(_provenance_evidence(fund.provenance, symbol, "fund"))
        if option_chain is not None:
            evidence.append(_provenance_evidence(option_chain.provenance, symbol, "options"))
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
            fundamentals=fundamentals,
            corporate_actions=corporate_actions,
            fund=fund,
            option_chain=option_chain,
            reconciliation=getattr(self._market_data, "last_reconciliation", None),
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


def _fundamental_evidence(item) -> EvidenceReference:
    reference = item.provenance.raw_reference or (
        f"{item.symbol}:{item.filing_type}:{item.period_end.isoformat()}"
    )
    return EvidenceReference(
        source=item.provenance.source,
        reference=reference,
        observed_at=item.provenance.available_at,
    )


def _provenance_evidence(provenance, symbol: str, kind: str) -> EvidenceReference:
    return EvidenceReference(
        source=provenance.source,
        reference=provenance.raw_reference or f"{symbol}:{kind}",
        observed_at=provenance.available_at,
    )


def _corporate_actions(bars) -> tuple[CorporateAction, ...]:
    actions = []
    for bar in bars:
        metadata = bar.provenance.metadata
        for key, kind in (
            ("dividend", CorporateActionKind.DIVIDEND),
            ("capital_gain", CorporateActionKind.CAPITAL_GAIN),
            ("stock_split", CorporateActionKind.SPLIT),
        ):
            value = float(metadata.get(key, 0.0) or 0.0)
            if value <= 0:
                continue
            actions.append(
                CorporateAction(
                    symbol=bar.symbol,
                    effective_at=bar.timestamp,
                    kind=kind,
                    value=value,
                    currency=bar.currency,
                    provenance=bar.provenance,
                )
            )
    return tuple(actions)
