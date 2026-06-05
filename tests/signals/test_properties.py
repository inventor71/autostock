"""PBT-03 invariants for the pure signal core (F61).

- detect_movers: every output cleared the threshold; outputs ⊆ inputs; in_universe correct.
- build_readthrough: affected_peers ⊆ universe; trigger never in its own peers.
- peers_of: a symbol is never its own peer.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from src.signals.movers import detect_movers
from src.signals.peer_map import PeerMap
from src.signals.readthrough import build_readthrough
from src.signals.records import Mover, MoverRow

_SYMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
symbols = st.sampled_from(_SYMS)
changes = st.floats(min_value=-40, max_value=40, allow_nan=False, allow_infinity=False)
ratios = st.floats(min_value=0, max_value=20, allow_nan=False, allow_infinity=False)

rows_strategy = st.lists(
    st.builds(MoverRow, symbol=symbols, change_pct=st.none() | changes,
              volume_ratio=st.none() | ratios, close=st.just(10.0)),
    max_size=12,
)
universe_strategy = st.sets(symbols, max_size=6)


@given(rows=rows_strategy, universe=universe_strategy,
       price_pct=st.floats(1, 20), vol_ratio=st.floats(1, 10),
       require=st.sampled_from(["any", "both"]))
def test_detect_movers_invariants(rows, universe, price_pct, vol_ratio, require):
    out = detect_movers(rows, price_pct=price_pct, vol_ratio=vol_ratio,
                        universe=universe, require=require, max_movers=100)
    input_syms = {r.symbol.upper() for r in rows}
    uni = {s.upper() for s in universe}
    for m in out:
        # output ⊆ input
        assert m.symbol in input_syms
        # cleared the configured threshold per the require rule
        price_ok = abs(m.change_pct) >= price_pct
        vol_ok = m.volume_ratio is not None and m.volume_ratio >= vol_ratio
        if require == "both":
            assert price_ok and vol_ok
        else:
            assert price_ok or vol_ok
        # in_universe flag is accurate
        assert m.in_universe == (m.symbol in uni)
        # direction matches sign
        assert m.direction == ("up" if m.change_pct >= 0 else "down")
    # sorted by |change| descending
    mags = [abs(m.change_pct) for m in out]
    assert mags == sorted(mags, reverse=True)


_GROUPS = {"g1": ["AAA", "BBB", "CCC"], "g2": ["CCC", "DDD"], "g3": ["EEE", "FFF"]}
_PM = PeerMap.from_config(_GROUPS)


@given(symbol=symbols)
def test_peers_never_include_self(symbol):
    assert symbol.upper() not in _PM.peers_of(symbol)


def _mover(sym, chg, uni):
    return Mover(symbol=sym, change_pct=chg, direction="up" if chg >= 0 else "down",
                 in_universe=sym in uni, qualified_by=["price"])


@given(
    movers=st.lists(st.tuples(symbols, changes), max_size=6),
    universe=universe_strategy,
    min_trigger=st.floats(1, 20),
)
def test_readthrough_invariants(movers, universe, min_trigger):
    uni = {s.upper() for s in universe}
    mover_objs = [_mover(s, c, uni) for s, c in movers]
    alerts = build_readthrough(mover_objs, _PM, uni, min_trigger_pct=min_trigger, max_peers=100)
    for a in alerts:
        assert abs(a.trigger_change_pct) >= min_trigger
        assert a.trigger_symbol not in a.affected_peers
        assert set(a.affected_peers) <= uni
        assert len(a.affected_peers) >= 1  # no empty alerts
