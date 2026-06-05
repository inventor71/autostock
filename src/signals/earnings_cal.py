"""Imminent-earnings selection — pure (F61, FR-4 / business-rule R3).

Filter a calendar to ``universe ∪ held`` inside the horizon, flag held names,
and attach peer read-through (held/universe peers of the reporting name).
"""

from __future__ import annotations

from datetime import date, timedelta

from src.signals.peer_map import PeerMap
from src.signals.records import EarningsRow, ImminentEarnings


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def select_imminent_earnings(
    rows: list[EarningsRow],
    universe: set[str],
    held: set[str],
    peer_map: PeerMap,
    *,
    horizon_days: int,
    today: date,
) -> list[ImminentEarnings]:
    """Return upcoming earnings for tracked names within ``[today, today+horizon]``.

    Pure. ``peer_readthrough`` = peers of the reporting name that are held or in
    universe — i.e. names whose theses may need a check around the report.
    """
    uni = {_norm(s) for s in universe}
    held_n = {_norm(s) for s in held}
    watch = uni | held_n
    horizon_end = today + timedelta(days=horizon_days)

    out: list[ImminentEarnings] = []
    for row in rows:
        sym = _norm(row.symbol)
        if sym not in watch:
            continue
        if not (today <= row.earnings_date <= horizon_end):
            continue
        peers = [p for p in peer_map.peers_of(sym) if p in watch and p != sym]
        out.append(
            ImminentEarnings(
                symbol=sym,
                earnings_date=row.earnings_date,
                when=row.when,
                eps_estimate=row.eps_estimate,
                is_held=sym in held_n,
                peer_readthrough=peers,
            )
        )

    # Soonest first, then symbol for determinism.
    out.sort(key=lambda e: (e.earnings_date, e.symbol))
    return out
