"""Small shared helpers for the F3 intraday subsystem."""

from __future__ import annotations


def held_and_watched(snapshot: dict | None, watch_store) -> list[str]:
    """Symbols the intraday loop should consider: held positions (from the
    snapshot, never the broker) ∪ active watch-trigger symbols, de-duplicated.
    Single source so the detector, brief, and news poller don't drift (review #9)."""
    held = list((snapshot or {}).get("positions", {}) or {})
    watched: list[str] = []
    if watch_store is not None:
        try:
            watched = [t.symbol for t in watch_store.active()]
        except Exception:
            watched = []
    return list(dict.fromkeys(held + watched))


def session_open(bars) -> float | None:
    """The current session's opening price = the open of the first bar of the
    latest calendar day in the window — NOT the oldest bar in a rolling window,
    which would be a ~4h-stale, forward-drifting anchor (review #4)."""
    if bars is None or len(bars) == 0:
        return None
    try:
        last_date = bars.index[-1].date()
        same_day = bars[[d.date() == last_date for d in bars.index]]
        src = same_day if len(same_day) else bars
        return float(src["open"].iloc[0])
    except Exception:
        try:
            return float(bars["open"].iloc[0])
        except Exception:
            return None
