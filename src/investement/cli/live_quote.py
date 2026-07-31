import argparse
import json
from datetime import UTC, datetime

from investement.data import build_market_data_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one current market quote with provenance")
    parser.add_argument("symbols", nargs="+", help="symbols such as AAPL or SPY")
    parser.add_argument(
        "--source",
        choices=("auto", "yfinance", "alpha-vantage"),
        default="auto",
    )
    parser.add_argument(
        "--entitlement",
        choices=("realtime", "delayed", ""),
        default="",
    )
    args = parser.parse_args()
    provider, config = build_market_data_provider(source=args.source, cache_directory=None)
    latest_quote = getattr(provider, "latest_quote", None)
    if latest_quote is None:
        raise RuntimeError(f"{provider.name} does not expose live quotes")
    quotes = []
    for symbol in args.symbols:
        try:
            quote = latest_quote(symbol, entitlement=args.entitlement)
        except TypeError:
            quote = latest_quote(symbol)
        quotes.append(
            {
                "symbol": quote.symbol,
                "last_price": quote.last_price,
                "bid": quote.bid,
                "ask": quote.ask,
                "volume": quote.volume,
                "retrieved_at": quote.provenance.retrieved_at.isoformat(),
                "source": quote.provenance.source,
                "metadata": dict(quote.provenance.metadata),
            }
        )
    print(json.dumps({"as_of": datetime.now(UTC).isoformat(), "provider": config, "quotes": quotes}, indent=2))


if __name__ == "__main__":
    main()
