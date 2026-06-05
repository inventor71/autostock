"""Static peer map + ``peers_of`` resolution (F61, FR-3).

A peer map is a set of named groups; ``peers_of(sym)`` is the union of co-members
across every group ``sym`` belongs to, minus ``sym`` itself. Pure and deterministic.
"""

from __future__ import annotations

from src.signals.records import PeerGroup


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


class PeerMap:
    """Resolves a symbol to its peers via the configured groups.

    Built once from config; ``peers_of`` is a pure lookup. Membership is
    case-insensitive and order-preserving (first-seen order across groups).
    """

    def __init__(self, groups: list[PeerGroup]):
        self.groups: list[PeerGroup] = groups
        # symbol -> ordered list of group names it belongs to
        self._sym_groups: dict[str, list[str]] = {}
        # group name -> ordered, de-duped member list (normalized)
        self._group_members: dict[str, list[str]] = {}
        for g in groups:
            seen: set[str] = set()
            members: list[str] = []
            for m in g.members:
                mn = _norm(m)
                if mn in seen:
                    continue
                seen.add(mn)
                members.append(mn)
                self._sym_groups.setdefault(mn, [])
                if g.name not in self._sym_groups[mn]:
                    self._sym_groups[mn].append(g.name)
            self._group_members[g.name] = members

    @classmethod
    def from_config(cls, peer_groups: dict[str, list[str]] | None) -> "PeerMap":
        """Build from the ``signals.peer_groups`` settings mapping."""
        peer_groups = peer_groups or {}
        return cls([PeerGroup(name=name, members=list(members))
                    for name, members in peer_groups.items()])

    def groups_of(self, symbol: str) -> list[str]:
        """Group names ``symbol`` belongs to (ordered, possibly empty)."""
        return list(self._sym_groups.get(_norm(symbol), []))

    def peers_of(self, symbol: str) -> list[str]:
        """Union of co-members across ``symbol``'s groups, excluding itself.

        Order: by group order, then member order within each group; de-duped.
        """
        sym = _norm(symbol)
        out: list[str] = []
        seen: set[str] = {sym}
        for gname in self._sym_groups.get(sym, []):
            for member in self._group_members.get(gname, []):
                if member in seen:
                    continue
                seen.add(member)
                out.append(member)
        return out
