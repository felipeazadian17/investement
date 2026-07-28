from datetime import UTC, date, datetime, time
from typing import Any


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol cannot be empty")
    if normalized.endswith(".US"):
        return normalized[:-3]
    if normalized.endswith(".HK"):
        numeric = normalized[:-3]
        if numeric.isdigit():
            return f"{numeric.zfill(4)}.HK"
    return normalized


def to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if hasattr(value, "to_pydatetime"):
        return to_utc_datetime(value.to_pydatetime())
    raise TypeError(f"unsupported timestamp type: {type(value).__name__}")


def scalar(row: Any, *names: str) -> float:
    for name in names:
        try:
            value = row[name]
        except (KeyError, TypeError):
            continue
        if hasattr(value, "iloc"):
            value = value.iloc[0]
        return float(value)
    raise KeyError(f"missing columns: {', '.join(names)}")
