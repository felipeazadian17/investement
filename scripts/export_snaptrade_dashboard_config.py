from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from investement.agents.snaptrade import SUPPORTED_POSITION_KINDS
from investement.brokers import ReadOnlySnapTradeClient
from investement.cli.snaptrade_connect import load_credentials
from investement.data import normalize_symbol


DEFAULT_SIMILAR_PORTFOLIOS = (
    {
        "name": "US quality benchmark",
        "holdings": (
            {"symbol": "QUAL", "quantity": 0.45},
            {"symbol": "SPY", "quantity": 0.35},
            {"symbol": "MOAT", "quantity": 0.20},
        ),
    },
    {
        "name": "Global equity blend",
        "holdings": (
            {"symbol": "SPY", "quantity": 0.50},
            {"symbol": "EFA", "quantity": 0.25},
            {"symbol": "EEM", "quantity": 0.15},
            {"symbol": "QQQ", "quantity": 0.10},
        ),
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export SnapTrade read-only positions into the Next.js dashboard config."
    )
    parser.add_argument("--output", default="portfolio.config.json")
    parser.add_argument("--base-currency", default="USD")
    parser.add_argument("--benchmark", default="SPY")
    args = parser.parse_args()

    credentials = load_credentials(interactive=False)
    portfolio = ReadOnlySnapTradeClient(credentials).portfolio(include_positions=True)
    holdings = _holdings(portfolio, args.base_currency)
    payload = {
        "baseCurrency": args.base_currency.upper(),
        "benchmark": args.benchmark.upper(),
        "similarPortfolios": DEFAULT_SIMILAR_PORTFOLIOS,
        "holdings": holdings,
    }
    Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": args.output, "positions": len(holdings)}, sort_keys=True))
    return 0


def _holdings(portfolio: Sequence[Mapping[str, Any]], base_currency: str) -> list[dict[str, float | str]]:
    currency = base_currency.upper()
    quantities: dict[str, float] = {}
    for account in portfolio:
        for position in account.get("positions", ()):
            if not isinstance(position, Mapping) or position.get("cash_equivalent") is True:
                continue
            instrument = position.get("instrument")
            if not isinstance(instrument, Mapping):
                continue
            kind = str(instrument.get("kind", "")).strip().casefold()
            if kind not in SUPPORTED_POSITION_KINDS:
                continue
            raw_symbol = str(instrument.get("symbol", "")).strip()
            if not raw_symbol:
                continue
            position_currency = _currency(position.get("currency") or instrument.get("currency"))
            if position_currency and position_currency != currency:
                continue
            symbol = normalize_symbol(raw_symbol)
            units = float(position.get("units", 0))
            if units > 0:
                quantities[symbol] = quantities.get(symbol, 0.0) + units
    return [
        {"symbol": symbol, "quantity": quantity}
        for symbol, quantity in sorted(quantities.items())
    ]


def _currency(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("code")
    return str(value or "").strip().upper()


if __name__ == "__main__":
    raise SystemExit(main())
