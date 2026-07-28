from collections.abc import Sequence
from datetime import date
from typing import Protocol

from investement.domain import PriceBar


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
    ) -> Sequence[object]: ...
