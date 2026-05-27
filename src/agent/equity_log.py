"""Append-only equity/P&L snapshot log — the paper account's track record.

One JSON line per snapshot (recorded at EOD by the agent loop, or on demand) so
the equity curve / daily returns can be plotted and used as the scorecard for
evaluating the agent over time. Lives under the gitignored workspace.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.core.models import PortfolioState


def snapshot(portfolio: PortfolioState) -> dict:
    """Build an equity/P&L snapshot dict from a portfolio state."""
    invested = sum(p.market_value for p in portfolio.positions.values())
    open_pnl = sum(p.unrealized_pnl for p in portfolio.positions.values())
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "date": datetime.now().date().isoformat(),
        "equity": round(portfolio.equity, 2),
        "cash": round(portfolio.cash, 2),
        "invested": round(invested, 2),
        "open_pnl": round(open_pnl, 2),
        "position_count": portfolio.position_count,
        "positions": [
            {
                "symbol": sym,
                "qty": p.qty,
                "avg": round(p.avg_entry_price, 2),
                "price": round(p.current_price, 2),
                "pnl": round(p.unrealized_pnl, 2),
            }
            for sym, p in sorted(portfolio.positions.items())
        ],
    }


def record_equity(portfolio: PortfolioState, path: str | Path) -> dict:
    """Append a snapshot of the account to the JSONL equity log; return it."""
    snap = snapshot(portfolio)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap) + "\n")
    logger.info(
        "Equity snapshot: ${:,.0f} (cash ${:,.0f}, open P&L {:+.2f}, {} positions)",
        snap["equity"], snap["cash"], snap["open_pnl"], snap["position_count"],
    )
    return snap


def read_equity(path: str | Path) -> list[dict]:
    """Read all equity snapshots (oldest first); [] if the log doesn't exist."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def default_path() -> Path:
    """Default equity log location (gitignored workspace)."""
    from src.agent.journal import Journal
    return Journal().root / "equity.jsonl"


def main() -> None:
    """Record one snapshot of the live (paper) account now: python -m src.agent.equity_log"""
    from config.config import get_settings
    from src.execution.brokers.alpaca_broker import AlpacaBroker

    s = get_settings()
    broker = AlpacaBroker(
        api_key=s.alpaca_api_key, secret_key=s.alpaca_secret_key, paper=s.broker.paper
    )
    record_equity(broker.get_portfolio_state(), default_path())


if __name__ == "__main__":
    main()
