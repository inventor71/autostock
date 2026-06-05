"""PBT-02 round-trip: every signal record serializes losslessly (F61).

``model_validate(x.model_dump(mode="json")) == x`` for all generated records.
Uses Hypothesis (PBT-09) with domain-appropriate generators (PBT-07).
"""

from __future__ import annotations

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from src.signals.records import (
    EarningsRow,
    ImminentEarnings,
    MarketSignalBrief,
    Mover,
    MoverRow,
    ReadThroughAlert,
)

# --- domain generators (PBT-07) ------------------------------------------- #
symbols = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=5)
changes = st.floats(min_value=-40, max_value=40, allow_nan=False, allow_infinity=False)
ratios = st.floats(min_value=0, max_value=20, allow_nan=False, allow_infinity=False)
prices = st.floats(min_value=0.01, max_value=5000, allow_nan=False, allow_infinity=False)
when = st.sampled_from(["bmo", "amc", "unknown"])
dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))


@st.composite
def movers(draw) -> Mover:
    chg = draw(changes)
    return Mover(
        symbol=draw(symbols), change_pct=chg,
        volume_ratio=draw(st.none() | ratios), close=draw(st.none() | prices),
        direction="up" if chg >= 0 else "down",
        in_universe=draw(st.booleans()),
        qualified_by=draw(st.lists(st.sampled_from(["price", "volume"]), max_size=2, unique=True)),
    )


@st.composite
def alerts(draw) -> ReadThroughAlert:
    return ReadThroughAlert(
        trigger_symbol=draw(symbols), trigger_change_pct=draw(changes),
        cause_hint=draw(st.none() | st.text(max_size=120)),
        affected_peers=draw(st.lists(symbols, max_size=8)),
        groups=draw(st.lists(symbols, max_size=4)),
    )


@st.composite
def imminent(draw) -> ImminentEarnings:
    return ImminentEarnings(
        symbol=draw(symbols), earnings_date=draw(dates), when=draw(when),
        eps_estimate=draw(st.none() | st.floats(min_value=-50, max_value=50,
                                                allow_nan=False, allow_infinity=False)),
        is_held=draw(st.booleans()),
        peer_readthrough=draw(st.lists(symbols, max_size=6)),
    )


def _roundtrip(model):
    cls = type(model)
    assert cls.model_validate(model.model_dump(mode="json")) == model


@given(st.builds(MoverRow, symbol=symbols, change_pct=st.none() | changes,
                volume_ratio=st.none() | ratios, close=st.none() | prices))
def test_mover_row_roundtrip(m):
    _roundtrip(m)


@given(movers())
def test_mover_roundtrip(m):
    _roundtrip(m)


@given(alerts())
def test_alert_roundtrip(a):
    _roundtrip(a)


@given(imminent())
def test_imminent_roundtrip(e):
    _roundtrip(e)


@given(st.builds(EarningsRow, symbol=symbols, earnings_date=dates, when=when,
                eps_estimate=st.none() | changes))
def test_earnings_row_roundtrip(e):
    _roundtrip(e)


@given(st.lists(movers(), max_size=5), st.lists(alerts(), max_size=5),
       st.lists(imminent(), max_size=5), st.lists(st.text(max_size=20), max_size=3))
def test_brief_roundtrip(ms, als, ims, degraded):
    brief = MarketSignalBrief(movers=ms, readthrough_alerts=als,
                              imminent_earnings=ims, degraded_sources=degraded)
    _roundtrip(brief)
