"""Unit tests for the static peer map (F61)."""

from src.signals.peer_map import PeerMap

_GROUPS = {
    "semiconductors": ["AVGO", "NVDA", "AMD", "MRVL"],
    "ai_networking": ["ANET", "AVGO", "MRVL"],
    "banks": ["JPM", "BAC"],
}


def _pm() -> PeerMap:
    return PeerMap.from_config(_GROUPS)


def test_peers_exclude_self():
    pm = _pm()
    assert "AVGO" not in pm.peers_of("AVGO")


def test_peers_union_across_groups():
    pm = _pm()
    peers = set(pm.peers_of("AVGO"))
    # from semiconductors + ai_networking, minus AVGO
    assert peers == {"NVDA", "AMD", "MRVL", "ANET"}


def test_peers_case_insensitive():
    pm = _pm()
    assert set(pm.peers_of("avgo")) == set(pm.peers_of("AVGO"))


def test_unknown_symbol_has_no_peers():
    pm = _pm()
    assert pm.peers_of("ZZZ") == []
    assert pm.groups_of("ZZZ") == []


def test_groups_of():
    pm = _pm()
    assert set(pm.groups_of("AVGO")) == {"semiconductors", "ai_networking"}


def test_no_cross_group_leak():
    pm = _pm()
    assert "JPM" not in pm.peers_of("AVGO")
    assert pm.peers_of("JPM") == ["BAC"]
