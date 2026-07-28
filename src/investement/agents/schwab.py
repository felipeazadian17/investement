from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from investement.agents.models import BrokerAccountSnapshot
from investement.brokers import ReadOnlySchwabClient


class SchwabExecutorAgent:
    """Phase-one Schwab agent with read capabilities only."""

    name = "schwab-executor-read-only"

    def __init__(
        self,
        client: ReadOnlySchwabClient,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock

    def read_portfolio(self, include_positions: bool = True) -> BrokerAccountSnapshot:
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("Schwab agent clock must return a timezone-aware datetime")
        return BrokerAccountSnapshot(
            retrieved_at=retrieved_at,
            account_numbers=tuple(self._client.account_numbers()),
            accounts=tuple(self._client.accounts(include_positions=include_positions)),
        )

    def read_account(
        self,
        account_hash: str,
        include_positions: bool = True,
    ) -> Mapping[str, Any]:
        return self._client.account(account_hash, include_positions=include_positions)

    def read_transactions(
        self,
        account_hash: str,
        start_date: Any,
        end_date: Any,
        transaction_types: Any,
        symbol: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return self._client.transactions(
            account_hash,
            start_date,
            end_date,
            transaction_types,
            symbol=symbol,
        )

    def read_quotes(self, symbols: Sequence[str]) -> Mapping[str, Any]:
        return self._client.quotes(symbols)
