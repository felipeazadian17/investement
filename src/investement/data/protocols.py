from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from investement.domain import FundamentalSnapshot, FundSnapshot, OptionChainSnapshot, PriceBar


class MarketDataProvider(Protocol):
    name: str

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> Sequence[PriceBar]: ...


class FilingProvider(Protocol):
    name: str

    def latest_filings(
        self,
        symbol: str,
        forms: Sequence[str],
        limit: int = 10,
        filed_after: date | None = None,
        available_before: datetime | None = None,
    ) -> Sequence[object]: ...


class FundamentalDataProvider(Protocol):
    name: str

    def latest_fundamentals(
        self,
        symbol: str,
        forms: Sequence[str],
        limit: int = 8,
        filed_after: date | None = None,
        available_before: datetime | None = None,
    ) -> Sequence[FundamentalSnapshot]: ...


class InstrumentDataProvider(Protocol):
    name: str

    def fund_snapshot(self, symbol: str, as_of: datetime) -> FundSnapshot | None: ...

    def option_chain(
        self,
        symbol: str,
        expiration: date,
        as_of: datetime,
    ) -> OptionChainSnapshot: ...
