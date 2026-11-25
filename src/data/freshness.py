"""Source timestamps and retrieval times have different meanings."""
from __future__ import annotations

import math
from datetime import UTC, datetime

import pandas as pd


def bar_metadata(bars, timeframe: str = "1d") -> dict:
    stamp = bars.index[-1] if bars is not None and len(bars) else None
    as_of = stamp.isoformat() if isinstance(stamp, (datetime, pd.Timestamp)) else None
    return {"source_as_of": as_of, "timeframe": timeframe, "price_kind": "bar_close"}


def latest_quote(provider, symbol: str) -> dict:
    """Preserve a source timestamp when supported; never invent one from now()."""
    method = getattr(provider, "get_latest_quote", None)
    if callable(method):
        result = dict(method(symbol))
    else:
        result = {"price": provider.get_latest_price(symbol), "source_as_of": None}
    price = float(result["price"])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Invalid latest price")
    return {**result, "price": price, "source_as_of": result.get("source_as_of"),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "source": type(provider).__name__}


def age_seconds(timestamp: str | None, now: datetime | None = None) -> float | None:
    if not timestamp:
        return None
    try:
        stamp = datetime.fromisoformat(timestamp)
        if stamp.tzinfo is None:
            return None  # Provider did not identify its timezone.
        return round(((now or datetime.now(UTC)) - stamp).total_seconds(), 1)
    except (ValueError, TypeError):
        return None
