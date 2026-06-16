"""Disclosed-holdings → research-brief highlights — source-agnostic, pure (F81, FR-5).

Builds compact, direction-explicit highlights (top LONG / top SHORT / NEW / EXIT)
from cached snapshots, and renders them as the brief line(s). A PUT shows under
SHORT so the agent never reads a bearish bet as bullish. No I/O here — the caller
reads snapshots + previous baselines from the store and passes them in.
"""

from __future__ import annotations

from datetime import date

from src.signals.holdings.records import (
    HoldingsHighlight,
    HoldingsSnapshot,
)
from src.signals.holdings.store import compute_diff, is_stale


def build_highlights(
    snapshots: list[HoldingsSnapshot],
    *,
    prev_by_id: dict[str, HoldingsSnapshot] | None = None,
    max_age_days: int,
    top_n: int = 6,
    today: date | None = None,
) -> list[HoldingsHighlight]:
    """One highlight per snapshot (pure). Highest-weight names first per side."""
    prev_by_id = prev_by_id or {}
    out: list[HoldingsHighlight] = []
    for snap in snapshots:
        longs = [r.ticker for r in _by_weight(snap) if r.side == "LONG"][:top_n]
        shorts = [r.ticker for r in _by_weight(snap) if r.side == "SHORT"][:top_n]
        diff = compute_diff(prev_by_id.get(snap.source_id), snap)
        out.append(
            HoldingsHighlight(
                source_id=snap.source_id,
                manager_name=snap.manager_name,
                as_of=snap.as_of,
                long_top=longs,
                short_top=shorts,
                new=diff.new[:top_n],
                exited=diff.exited[:top_n],
                unmapped_n=snap.unmapped_n,
                stale=is_stale(snap, max_age_days=max_age_days, today=today),
            )
        )
    return out


def _by_weight(snap: HoldingsSnapshot):
    return sorted(snap.rows, key=lambda r: r.weight, reverse=True)


def render_line(h: HoldingsHighlight) -> str:
    """Full human-readable line (LONG + SHORT + diff) for debug/human rendering of the
    on-demand pull data. 13F is NOT pushed into the every-turn brief (F89 — it is
    reference-only, surfaced via the ``disclosed_holdings`` tool)."""
    parts: list[str] = []
    if h.long_top:
        parts.append("LONG " + ",".join(h.long_top))
    if h.short_top:
        parts.append("SHORT " + ",".join(h.short_top))
    if h.new:
        parts.append("NEW " + ",".join(h.new))
    if h.exited:
        parts.append("EXIT " + ",".join(h.exited))
    if h.unmapped_n:
        parts.append(f"unmapped {h.unmapped_n}")
    stale = " [stale]" if h.stale else ""
    body = " · ".join(parts) if parts else "(no mapped holdings)"
    return f"[기관공시] {h.manager_name} (13F {h.as_of.isoformat()}){stale}: {body}"
