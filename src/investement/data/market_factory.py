import os
from pathlib import Path

from investement.data.alpha_vantage_provider import AlphaVantageProvider
from investement.data.cache import CachedMarketDataProvider, JsonPriceBarCache
from investement.data.reconciled_provider import ReconciledMarketDataProvider
from investement.data.yfinance_provider import YFinanceProvider


def build_market_data_provider(
    *,
    source: str = "auto",
    cross_check: str = "none",
    cache_directory: Path | None = Path(".cache/market"),
    alpha_outputsize: str = "full",
):
    """Build the configured read-only market feed.

    ``auto`` prefers Alpha Vantage only when a key is configured; otherwise it
    uses Yahoo for research/backtesting. A second source is never silently
    substituted: a requested cross-check without credentials is an error.
    """

    source = source.strip().casefold()
    cross_check = cross_check.strip().casefold()
    if source not in {"auto", "yfinance", "alpha-vantage"}:
        raise ValueError("source must be auto, yfinance, or alpha-vantage")
    if cross_check not in {"none", "yfinance", "alpha-vantage"}:
        raise ValueError("cross_check must be none, yfinance, or alpha-vantage")
    api_key = _setting("ALPHA_VANTAGE_API_KEY")
    if source == "auto":
        source = "alpha-vantage" if api_key else "yfinance"
    if source == "alpha-vantage" and not api_key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is required for alpha-vantage market data")

    def make(name: str):
        if name == "yfinance":
            return YFinanceProvider()
        if not api_key:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is required for alpha-vantage market data")
        return AlphaVantageProvider(api_key, outputsize=alpha_outputsize, adjusted=True)

    cache = JsonPriceBarCache(cache_directory) if cache_directory is not None else None

    def cached(provider):
        return CachedMarketDataProvider(provider, cache) if cache is not None else provider

    primary = cached(make(source))
    if cross_check == "none":
        return primary, {"primary": source, "secondary": None, "reconciled": False}
    if cross_check == source:
        raise ValueError("cross_check must differ from the primary source")
    secondary = cached(make(cross_check))
    return (
        ReconciledMarketDataProvider(primary, secondary),
        {"primary": source, "secondary": cross_check, "reconciled": True},
    )


def _setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = Path(".env.local")
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, candidate = stripped.split("=", 1)
        if key.strip() == name:
            return candidate.strip().strip("\"'")
    return ""
