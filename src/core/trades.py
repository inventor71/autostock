"""FIFO round-trip matching: turn a fill stream into closed trades.

A pure, dependency-free helper shared by the live agent ledger
(``src/agent/trades_log.py``) and the backtest engine — so realized P&L,
win rate, and profit factor are computed the same way in simulation and live.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def match_round_trips(fills: list[dict]) -> list[dict]:
    """FIFO-match fills into closed round-trips.

    Each fill: ``{"symbol", "side": "buy"|"sell", "qty", "price", "ts"}`` (ts
    ISO-8601, sortable). A sell closes the oldest open buy lots; each closed lot
    yields one round-trip record. Open (unsold) lots produce nothing.
    """
    lots: dict[str, deque] = defaultdict(deque)  # symbol -> open buy lots [qty, price, ts]
    trades: list[dict] = []
    for f in sorted(fills, key=lambda x: x["ts"]):
        sym, qty, price, ts = f["symbol"], float(f["qty"]), float(f["price"]), f["ts"]
        if str(f["side"]).lower() == "buy":
            lots[sym].append([qty, price, ts])
            continue
        remaining = qty
        while remaining > 1e-9 and lots[sym]:
            lot = lots[sym][0]
            take = min(remaining, lot[0])
            entry = lot[1]
            trades.append({
                "symbol": sym,
                "qty": round(take, 6),
                "entry_price": round(entry, 2),
                "exit_price": round(price, 2),
                "opened_at": lot[2],
                "closed_at": ts,
                "realized_pnl": round((price - entry) * take, 2),
                "return_pct": round((price / entry - 1) * 100, 2) if entry else 0.0,
            })
            lot[0] -= take
            remaining -= take
            if lot[0] <= 1e-9:
                lots[sym].popleft()
    return trades


def _to_et(ts: str) -> datetime | None:
    """Parse an ISO-8601 ``closed_at`` (UTC or tz-aware) and convert to ET.

    Naive timestamps are assumed UTC (Alpaca ``filled_at`` is UTC). Returns None
    on unparseable input so callers can skip it without crashing.
    """
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_ET)


def summarize_today_round_trips(fills: list[dict], *, now_et: datetime | None = None) -> dict:
    """Summarize *today's* (ET) closed round-trips for the steering read view.

    Round-trips are matched over the FULL fill stream (an opening buy may predate
    today), then filtered to those whose ``closed_at`` falls on the current ET
    date — so the summary reflects realized P&L *today*, not the lifetime ledger.
    Empty / all-prior → ``win_rate=None`` (rendered as an empty state, fail-soft).

    ``fills`` are dicts ``{symbol, side, qty, price, ts}``; the daemon converts the
    broker's ``FillEvent`` stream (F3 ``get_fills``) into this shape. Pure: ``now_et``
    is injectable for deterministic tests (UTC→ET boundary).
    """
    now_et = now_et or datetime.now(_ET)
    today = now_et.date()
    todays = []
    for t in match_round_trips(fills):
        closed = _to_et(t.get("closed_at"))
        if closed is not None and closed.date() == today:
            todays.append(t)
    n = len(todays)
    as_of = now_et.isoformat(timespec="seconds")
    if n == 0:
        return {"closed_count": 0, "win_rate": None, "realized_pnl": 0.0, "as_of": as_of}
    wins = sum(1 for t in todays if t["realized_pnl"] > 0)
    return {
        "closed_count": n,
        "win_rate": round(wins / n, 4),
        "realized_pnl": round(sum(t["realized_pnl"] for t in todays), 2),
        "as_of": as_of,
    }
