"""Unit tests for read-through propagation (F61, R2)."""

from src.signals.peer_map import PeerMap
from src.signals.records import Mover
from src.signals.readthrough import build_readthrough

_PM = PeerMap.from_config({
    "semis": ["AVGO", "NVDA", "AMD", "MRVL"],
    "energy": ["XLE", "XOM", "CVX"],
})
_UNI = {"AVGO", "NVDA", "AMD", "MRVL", "XOM", "CVX"}


def _mover(sym, chg):
    return Mover(symbol=sym, change_pct=chg, direction="up" if chg >= 0 else "down",
                 in_universe=sym in _UNI, qualified_by=["price"])


def test_trigger_below_threshold_no_alert():
    out = build_readthrough([_mover("AVGO", -6.0)], _PM, _UNI, min_trigger_pct=7.0)
    assert out == []


def test_affected_peers_subset_of_universe_and_exclude_trigger():
    out = build_readthrough([_mover("AVGO", -10.0)], _PM, _UNI, min_trigger_pct=7.0)
    assert len(out) == 1
    alert = out[0]
    assert alert.trigger_symbol == "AVGO"
    assert "AVGO" not in alert.affected_peers
    assert set(alert.affected_peers) <= _UNI
    assert set(alert.affected_peers) == {"NVDA", "AMD", "MRVL"}


def test_out_of_universe_trigger_still_propagates_to_universe_peers():
    # XLE is a bellwether (not in universe) but still triggers energy read-through.
    out = build_readthrough([_mover("XLE", 9.0)], _PM, _UNI, min_trigger_pct=7.0)
    assert out and set(out[0].affected_peers) == {"XOM", "CVX"}
    assert "XLE" not in out[0].affected_peers


def test_no_peers_no_alert():
    pm = PeerMap.from_config({"semis": ["AVGO", "NVDA"]})
    out = build_readthrough([_mover("ZZZ", -12.0)], pm, {"ZZZ"}, min_trigger_pct=7.0)
    assert out == []


def test_max_peers_cap():
    out = build_readthrough([_mover("AVGO", -10.0)], _PM, _UNI, min_trigger_pct=7.0, max_peers=2)
    assert len(out[0].affected_peers) == 2
