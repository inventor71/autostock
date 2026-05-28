"""Closed round-trip ledger (trades.jsonl): the agent's realized track record.

Reconstructs closed trades from fills by FIFO matching (buys -> sells per
symbol), giving realized P&L / return% / hold time per round-trip — the basis
for win rate, profit factor, and expectancy. R-multiple and decision/exit-reason
attribution are TODO (need the originating stop and the exit order type).
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


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


def _trade_key(t: dict) -> str:
    return f"{t['symbol']}|{t['opened_at']}|{t['closed_at']}|{t['qty']}"


def _alpaca_fills(client, since: str | None = None, min_notional: float = 0.0) -> list[dict]:
    """Pull filled orders from Alpaca as fills for matching.

    ``since`` (ISO date) drops fills before the experiment began — and is passed
    to the API as ``after`` so fewer orders are fetched. ``min_notional`` drops
    tiny penny/test fills. Together they keep pre-experiment test trades out of
    the ledger entirely (the agent never sees them).
    """
    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since) if isinstance(since, str) else since
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        kwargs = {"status": QueryOrderStatus.CLOSED, "limit": 500}
        if since_dt is not None:
            kwargs["after"] = since_dt  # fetch fewer orders (exclude pre-experiment)
        orders = client.get_orders(filter=GetOrdersRequest(**kwargs))
    except Exception as e:
        logger.warning(f"Could not fetch fills for trade ledger: {e}")
        return []
    fills = []
    for o in orders:
        if not o.filled_at or float(o.filled_qty or 0) <= 0:
            continue
        if since_dt is not None and o.filled_at < since_dt:
            continue  # pre-experiment test trade
        qty = float(o.filled_qty)
        price = float(o.filled_avg_price or 0)
        if qty * price < min_notional:
            continue  # penny / test fill
        fills.append({
            "symbol": o.symbol,
            "side": str(o.side).split(".")[-1].lower(),
            "qty": qty,
            "price": price,
            "ts": o.filled_at.isoformat() if hasattr(o.filled_at, "isoformat") else str(o.filled_at),
        })
    return fills


def record_trades(client, path: str | Path, since: str | None = None, min_notional: float = 0.0) -> list[dict]:
    """Reconstruct closed round-trips from the broker's fills and append any new
    ones to ``trades.jsonl`` (idempotent — recomputes all, writes only new)."""
    path = Path(path)
    existing = {_trade_key(t) for t in read_trades(path)}
    fills = _alpaca_fills(client, since=since, min_notional=min_notional)
    new = [t for t in match_round_trips(fills) if _trade_key(t) not in existing]
    if not new:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for t in new:
            fh.write(json.dumps(t) + "\n")
    realized = sum(t["realized_pnl"] for t in new)
    logger.info("Trade ledger: +{} closed round-trip(s), realized {:+.2f}", len(new), realized)
    return new


def read_trades(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
