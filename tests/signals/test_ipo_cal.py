"""Imminent-IPO selection (F78) — examples + property-based invariants.

PBT (Partial, per F78 extension config): the pure selector's ordering/cap/horizon
invariants and the IpoRow/ImminentIpo serialization round-trip.
"""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from src.signals.ipo_cal import select_imminent_ipos
from src.signals.records import ImminentIpo, IpoRow

_TODAY = date(2026, 6, 13)


def _row(name, *, symbol=None, day=0, status="expected", value=None):
    return IpoRow(name=name, symbol=symbol, ipo_date=_TODAY + timedelta(days=day),
                  status=status, est_value=value)


# --- examples ------------------------------------------------------------- #
def test_horizon_filter_inclusive_bounds():
    rows = [
        _row("today", day=0, value=5),
        _row("edge", day=5, value=4),       # horizon end inclusive
        _row("beyond", day=6, value=9),     # outside
        _row("past", day=-1, value=9),      # already listed
    ]
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=5, max_ipos=8,
                               universe=set(), held=set())
    assert [i.name for i in out] == ["today", "edge"]


def test_withdrawn_excluded():
    rows = [_row("live", day=1, value=1), _row("dead", day=1, status="withdrawn", value=9)]
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=5, max_ipos=8,
                               universe=set(), held=set())
    assert [i.name for i in out] == ["live"]


def test_not_universe_filtered_but_tagged():
    rows = [_row("InUni", symbol="aapl", day=1, value=2),
            _row("Outsider", symbol="SPCX", day=1, value=3)]
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=5, max_ipos=8,
                               universe={"AAPL"}, held=set())
    # both surface (no universe filter); only the universe one is tagged
    assert {i.name for i in out} == {"InUni", "Outsider"}
    tags = {i.name: i.in_universe for i in out}
    assert tags == {"InUni": True, "Outsider": False}


def test_held_tag():
    rows = [_row("Held", symbol="spcx", day=1, value=2)]
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=5, max_ipos=8,
                               universe=set(), held={"SPCX"})
    assert out[0].is_held is True


def test_size_rank_then_cap():
    rows = [_row(f"n{i}", day=1, value=float(i)) for i in range(10)]
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=5, max_ipos=3,
                               universe=set(), held=set())
    assert [i.name for i in out] == ["n9", "n8", "n7"]  # biggest first, capped at 3


def test_missing_size_sorts_last():
    rows = [_row("noval", day=1, value=None), _row("hasval", day=1, value=1.0)]
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=5, max_ipos=8,
                               universe=set(), held=set())
    assert [i.name for i in out] == ["hasval", "noval"]


def test_symbol_normalized():
    out = select_imminent_ipos([_row("x", symbol=" spcx ", day=1, value=1)],
                               today=_TODAY, horizon_days=5, max_ipos=8,
                               universe=set(), held=set())
    assert out[0].symbol == "SPCX"


# --- property-based invariants -------------------------------------------- #
names = st.text(alphabet="ABCDEFGHIJKLMNOP", min_size=1, max_size=6)
values = st.none() | st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False)
status = st.sampled_from(["expected", "priced", "withdrawn", "filed", "unknown"])
days = st.integers(min_value=-10, max_value=20)


@st.composite
def ipo_rows(draw):
    return IpoRow(name=draw(names), symbol=draw(st.none() | names),
                  ipo_date=_TODAY + timedelta(days=draw(days)),
                  status=draw(status), est_value=draw(values))


@given(rows=st.lists(ipo_rows(), max_size=20),
       horizon=st.integers(0, 15), cap=st.integers(1, 10))
def test_invariants(rows, horizon, cap):
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=horizon, max_ipos=cap,
                               universe=set(), held=set())
    # cap respected
    assert len(out) <= cap
    # every survivor is in-window and not withdrawn
    end = _TODAY + timedelta(days=horizon)
    for i in out:
        assert _TODAY <= i.ipo_date <= end
        assert i.status != "withdrawn"
    # size order: non-None values are non-increasing, and any None sorts after a value
    seen_none = False
    prev = None
    for i in out:
        if i.est_value is None:
            seen_none = True
        else:
            assert not seen_none, "a sized IPO must not follow an unsized one"
            if prev is not None:
                assert i.est_value <= prev + 1e-6
            prev = i.est_value


@given(rows=st.lists(ipo_rows(), max_size=15))
def test_idempotent(rows):
    once = select_imminent_ipos(rows, today=_TODAY, horizon_days=7, max_ipos=8,
                                universe=set(), held=set())
    twice = select_imminent_ipos(rows, today=_TODAY, horizon_days=7, max_ipos=8,
                                 universe=set(), held=set())
    assert [i.model_dump() for i in once] == [i.model_dump() for i in twice]


# --- record round-trip (PBT-02 sibling) ----------------------------------- #
@given(rows=st.lists(ipo_rows(), max_size=10))
def test_iporow_roundtrip(rows):
    for r in rows:
        assert IpoRow.model_validate(r.model_dump(mode="json")) == r


@given(rows=st.lists(ipo_rows(), max_size=10))
def test_imminentipo_roundtrip(rows):
    out = select_imminent_ipos(rows, today=_TODAY, horizon_days=10, max_ipos=10,
                               universe=set(), held=set())
    for i in out:
        assert ImminentIpo.model_validate(i.model_dump(mode="json")) == i
