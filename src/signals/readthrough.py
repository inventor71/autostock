"""Read-through propagation — pure (F61, FR-3 / business-rule R2).

For each mover whose move clears ``min_trigger_pct``, surface the **universe**
peers it may read through to (via the static peer map). Python proposes the
candidates; the agent decides whether the read-through is real.
"""

from __future__ import annotations

from src.signals.peer_map import PeerMap
from src.signals.records import Mover, ReadThroughAlert


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def build_readthrough(
    movers: list[Mover],
    peer_map: PeerMap,
    universe: set[str],
    *,
    min_trigger_pct: float,
    max_peers: int = 8,
) -> list[ReadThroughAlert]:
    """One alert per qualifying trigger mover that has at least one universe peer.

    Pure. ``affected_peers`` ⊆ ``universe`` and never contains the trigger itself.
    Movers themselves (other names that already moved) are not excluded as peers —
    a peer that also moved is still a valid read-through to flag.
    """
    uni = {_norm(s) for s in universe}
    alerts: list[ReadThroughAlert] = []

    for m in movers:
        if abs(m.change_pct) < min_trigger_pct:
            continue
        trigger = _norm(m.symbol)
        peers = [p for p in peer_map.peers_of(trigger) if p in uni and p != trigger]
        if not peers:
            continue
        alerts.append(
            ReadThroughAlert(
                trigger_symbol=trigger,
                trigger_change_pct=m.change_pct,
                cause_hint=None,  # filled by the collector from news, if available
                affected_peers=peers[:max_peers],
                groups=peer_map.groups_of(trigger),
            )
        )

    # Biggest trigger move first.
    alerts.sort(key=lambda a: (-abs(a.trigger_change_pct), a.trigger_symbol))
    return alerts
