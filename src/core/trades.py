"""FIFO round-trip matching: turn a fill stream into closed trades.

A pure, dependency-free helper shared by the live agent ledger
(``src/agent/trades_log.py``) and the backtest engine — so realized P&L,
win rate, and profit factor are computed the same way in simulation and live.
"""

from __future__ import annotations

from collections import defaultdict, deque


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
