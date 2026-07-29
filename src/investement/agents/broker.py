from typing import Protocol, runtime_checkable

from investement.agents.models import BrokerAccountSnapshot, BrokerPortfolioState


@runtime_checkable
class BrokerPortfolioReader(Protocol):
    name: str

    def read_portfolio(self, include_positions: bool = True) -> BrokerAccountSnapshot: ...


@runtime_checkable
class BrokerPortfolioStateReader(BrokerPortfolioReader, Protocol):
    def current_portfolio(self, base_currency: str = "USD") -> BrokerPortfolioState: ...
