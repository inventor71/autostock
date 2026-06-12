"""Outcome assembly for the end-of-day self-review turn.

The EOD turn learns only if it can compare each call to what actually happened.
This builds a compact, authoritative snapshot per recent decision — current
price vs the planned entry/stop/target, whether it's held and its P&L — from the
broker and data provider, so the agent grades against facts (not just its
memory) and distills generalizable lessons into ``lessons.md``.
"""

from __future__ import annotations

from src.agent.journal import Decision


def _safe_price(data_provider, symbol: str) -> float | None:
    try:
        return float(data_provider.get_latest_price(symbol))
    except Exception:
        return None


def _status(d: Decision, price: float | None, held: bool) -> str:
    if held:
        if d.target is not None and price is not None and price >= d.target:
            return "at/above target"
        if d.stop is not None and price is not None and price <= d.stop:
            return "at/below stop"
        return "open"
    if d.action == "BUY" and d.limit is not None and price is not None and price > d.limit:
        return "entry pending (price above limit)"
    if d.action == "HOLD":
        return "hold"
    return "flat/closed"


def outcome_lines(decisions, broker, data_provider, lookback: int = 20) -> list[str]:
    """One line per recent decision: levels, current price, holding, P&L, status."""
    lines: list[str] = []
    for d in decisions[-lookback:]:
        price = _safe_price(data_provider, d.symbol)
        try:
            pos = broker.get_position(d.symbol)
        except Exception:
            pos = None
        held = pos is not None and getattr(pos, "qty", 0) > 0

        # F54: P&L% is direction-aware. A short gains as price falls — using the
        # long formula here would report a winning short as a loss and mislead the
        # agent's own EOD review.
        pos_side = getattr(getattr(pos, "side", None), "value", "long") if held else "long"
        unrealized_pct = None
        if held and price is not None and pos.avg_entry_price > 0:
            if pos_side == "short":
                unrealized_pct = (pos.avg_entry_price / price - 1) * 100
            else:
                unrealized_pct = (price / pos.avg_entry_price - 1) * 100

        parts = [f"{d.symbol} {d.action}"]
        levels = []
        if d.limit is not None:
            levels.append(f"entry {d.limit}")
        if d.stop is not None:
            levels.append(f"stop {d.stop}")
        if d.target is not None:
            levels.append(f"target {d.target}")
        if levels:
            parts.append("(" + ", ".join(levels) + ")")
        if price is not None:
            parts.append(f"now {price:.2f}")
        if held:
            label = "SHORT " if pos_side == "short" else ""
            holding = f"held {label}{pos.qty:.0f}@{pos.avg_entry_price:.2f}"
            if unrealized_pct is not None:
                holding += f" {unrealized_pct:+.1f}%"
            parts.append(holding)
        parts.append(f"-> {_status(d, price, held)}")
        lines.append(" | ".join(parts))
    return lines
