"""Domain records for early-session signal detection.

BarRecord, SignalEvent, and EventIndex are pydantic models with JSONL
serialization helpers. See F47 ``src/surge/records.py`` for the equivalent
surge-detection records.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
from pydantic import BaseModel, Field


class BarRecord(BaseModel):
    """A single OHLCV bar stored in the per-symbol circular buffer."""

    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    vwap: float | None = None

    @classmethod
    def from_alpaca_bar(cls, symbol: str, ts, row) -> BarRecord:
        """Build from a row of an Alpaca bars DataFrame."""
        return cls(
            timestamp=ts,
            symbol=symbol,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)),
            vwap=float(row["vwap"]) if "vwap" in row and not pd.isna(row["vwap"]) else None,
        )


class SignalEvent(BaseModel):
    """Emitted when a symbol's price movement crosses the detection threshold."""

    symbol: str
    date: date
    detected_at: datetime
    direction: str  # "surge" | "drop"
    trigger_pct: float
    trigger_window_min: int
    open: float
    prev_close: float
    gap_pct: float


class EventIndex(BaseModel):
    """One line of ``_index.jsonl`` — metadata for a completed event dump."""

    symbol: str
    date: str  # YYYY-MM-DD
    detected_at: str  # ISO 8601
    direction: str
    trigger_pct: float
    trigger_window_min: int
    open: float
    prev_close: float
    gap_pct: float
    data_file: str  # relative path
    bar_count: int
    time_range_start: str  # ISO 8601
    time_range_end: str  # ISO 8601


# ---------------------------------------------------------------------------
# JSONL serialization helpers (stdlib json — no extra deps)
# ---------------------------------------------------------------------------

def bar_to_jsonl(bar: BarRecord) -> str:
    """Serialize a single BarRecord as a compact JSON line."""
    d = {
        "t": bar.timestamp.isoformat(),
        "o": bar.open,
        "h": bar.high,
        "l": bar.low,
        "c": bar.close,
        "v": bar.volume,
    }
    if bar.vwap is not None:
        d["vw"] = bar.vwap
    return json.dumps(d, separators=(",", ":"))


def bar_from_jsonl(line: str, symbol: str) -> BarRecord:
    """Deserialize a BarRecord from a compact JSON line."""
    d = json.loads(line)
    return BarRecord(
        timestamp=datetime.fromisoformat(d["t"]),
        symbol=symbol,
        open=d["o"],
        high=d["h"],
        low=d["l"],
        close=d["c"],
        volume=d.get("v", 0.0),
        vwap=d.get("vw"),
    )


def event_index_to_jsonl(record: EventIndex) -> str:
    """Serialize an EventIndex as a JSON line."""
    return json.dumps(record.model_dump(mode="json"), separators=(",", ":"))


def event_index_from_jsonl(line: str) -> EventIndex:
    """Deserialize an EventIndex from a JSON line."""
    return EventIndex.model_validate(json.loads(line))


