"""Closed round-trip ledger (trades.jsonl): the agent's realized track record.

Reconstructs closed trades from fills by FIFO matching (buys -> sells per
symbol), giving realized P&L / return% / hold time per round-trip — the basis
for win rate, profit factor, and expectancy. R-multiple and decision/exit-reason
attribution are TODO (need the originating stop and the exit order type).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

# match_round_trips moved to src/core/trades.py so the backtest engine can share
# the exact same FIFO matching; re-exported here for existing callers/tests.
from src.core.trades import match_round_trips  # noqa: F401 (re-exported)


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
