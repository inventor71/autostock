"""Holdings core (F81): records round-trip, store I/O + diff + staleness, overlay
direction-gating, brief highlights/render. Pure + fail-honest, no network.
"""

from __future__ import annotations

import json
from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from src.signals.holdings.brief import build_highlights, render_line
from src.signals.holdings.overlay import holdings_universe_overlay
from src.signals.holdings.records import (
    HoldingRow,
    HoldingsHighlight,
    HoldingsSnapshot,
)
from src.signals.holdings.store import (
    compute_diff,
    is_stale,
    read_prev,
    read_snapshots,
    write_snapshot,
)

# --- generators ------------------------------------------------------------ #
symbols = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=5)
sides = st.sampled_from(["LONG", "SHORT"])
weights = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)
dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))


@st.composite
def rows(draw):
    return HoldingRow(ticker=draw(symbols), side=draw(sides), weight=draw(weights))


@st.composite
def snapshots(draw):
    return HoldingsSnapshot(
        source_id=draw(st.text(min_size=1, max_size=8)),
        manager_name=draw(st.text(min_size=1, max_size=8)),
        as_of=draw(dates),
        rows=draw(st.lists(rows(), max_size=6)),
        unmapped_n=draw(st.integers(min_value=0, max_value=20)),
    )


# --------------------------------------------------------------------------- #
# Round-trip (PBT)
# --------------------------------------------------------------------------- #
@given(snapshots())
def test_snapshot_roundtrip(snap):
    assert HoldingsSnapshot.model_validate(snap.model_dump(mode="json")) == snap


@given(
    st.builds(
        HoldingsHighlight,
        source_id=st.text(min_size=1, max_size=8),
        manager_name=st.text(min_size=1, max_size=8),
        as_of=dates,
        long_top=st.lists(symbols, max_size=4),
        short_top=st.lists(symbols, max_size=4),
        stale=st.booleans(),
    )
)
def test_highlight_roundtrip(h):
    assert HoldingsHighlight.model_validate(h.model_dump(mode="json")) == h


# --------------------------------------------------------------------------- #
# Store: write/read/rotate/diff/staleness/fail-honest
# --------------------------------------------------------------------------- #
def _snap(source_id="sec_13f:1", as_of=date(2026, 3, 31), tickers=(("NVDA", "SHORT"), ("CLSK", "LONG"))):
    return HoldingsSnapshot(
        source_id=source_id, manager_name="SA LP", as_of=as_of,
        rows=[HoldingRow(ticker=t, side=s, weight=0.5) for t, s in tickers],
    )


def test_write_then_read_roundtrips(tmp_path):
    snap = _snap()
    assert write_snapshot(snap, root=tmp_path) is not None
    got = read_snapshots(root=tmp_path)
    assert len(got) == 1 and got[0].source_id == snap.source_id


def test_rotation_enables_diff_on_newer_filing(tmp_path):
    write_snapshot(_snap(as_of=date(2025, 12, 31), tickers=(("NVDA", "SHORT"), ("AAPL", "LONG"))), root=tmp_path)
    write_snapshot(_snap(as_of=date(2026, 3, 31), tickers=(("NVDA", "SHORT"), ("CLSK", "LONG"))), root=tmp_path)
    prev = read_prev("sec_13f:1", root=tmp_path)
    cur = read_snapshots(root=tmp_path)[0]
    diff = compute_diff(prev, cur)
    assert diff.new == ["CLSK"] and diff.exited == ["AAPL"]


def test_refetch_same_filing_does_not_rotate_baseline(tmp_path):
    # First two writes establish a real prev; a third write of the SAME report date
    # must not clobber that older baseline (as_of did not advance).
    write_snapshot(_snap(as_of=date(2025, 12, 31), tickers=(("AAPL", "LONG"),)), root=tmp_path)
    write_snapshot(_snap(as_of=date(2026, 3, 31), tickers=(("CLSK", "LONG"),)), root=tmp_path)
    write_snapshot(_snap(as_of=date(2026, 3, 31), tickers=(("CLSK", "LONG"), ("RIOT", "LONG"))), root=tmp_path)
    prev = read_prev("sec_13f:1", root=tmp_path)
    assert prev is not None and prev.as_of == date(2025, 12, 31)


def test_read_skips_corrupt_file(tmp_path):
    d = tmp_path / "holdings"
    d.mkdir()
    (d / "sec_13f_1.json").write_text("{ not json", encoding="utf-8")
    write_snapshot(_snap(source_id="sec_13f:2"), root=tmp_path)
    got = read_snapshots(root=tmp_path)
    assert [s.source_id for s in got] == ["sec_13f:2"]  # corrupt skipped, good kept


def test_read_missing_dir_is_empty(tmp_path):
    assert read_snapshots(root=tmp_path / "nope") == []


def test_is_stale():
    snap = _snap(as_of=date(2026, 1, 1))
    assert is_stale(snap, max_age_days=135, today=date(2026, 6, 1)) is True
    assert is_stale(snap, max_age_days=135, today=date(2026, 3, 1)) is False


def test_compute_diff_no_prev_is_empty():
    d = compute_diff(None, _snap())
    assert d.new == [] and d.exited == []


# --------------------------------------------------------------------------- #
# Overlay: direction gating (FR-4) — the safety-critical behavior
# --------------------------------------------------------------------------- #
def _mixed_snap():
    return HoldingsSnapshot(
        source_id="sec_13f:1", manager_name="SA LP", as_of=date(2026, 3, 31),
        rows=[
            HoldingRow(ticker="CLSK", side="LONG", weight=0.4),
            HoldingRow(ticker="NVDA", side="SHORT", weight=0.6),
        ],
    )


def test_overlay_long_only_when_shorting_disabled():
    out = holdings_universe_overlay(
        [_mixed_snap()], {"sec_13f:1"},
        shorting_enabled=False, max_age_days=135, today=date(2026, 4, 1))
    assert out == ["CLSK"]  # PUT underlying NVDA is NOT a universe candidate


def test_overlay_includes_short_when_shorting_enabled():
    out = holdings_universe_overlay(
        [_mixed_snap()], {"sec_13f:1"},
        shorting_enabled=True, max_age_days=135, today=date(2026, 4, 1))
    assert out == ["CLSK", "NVDA"]


def test_overlay_excludes_stale_snapshot():
    out = holdings_universe_overlay(
        [_mixed_snap()], {"sec_13f:1"},
        shorting_enabled=True, max_age_days=30, today=date(2026, 9, 1))
    assert out == []


def test_overlay_respects_source_allowlist():
    out = holdings_universe_overlay(
        [_mixed_snap()], set(),  # source not opted into overlay
        shorting_enabled=True, max_age_days=135, today=date(2026, 4, 1))
    assert out == []


# --------------------------------------------------------------------------- #
# Brief: highlights + render keep direction explicit (FR-5)
# --------------------------------------------------------------------------- #
def test_render_line_separates_long_and_short():
    hs = build_highlights([_mixed_snap()], max_age_days=135, today=date(2026, 4, 1))
    line = render_line(hs[0])
    assert "LONG CLSK" in line and "SHORT NVDA" in line


def test_highlight_marks_stale_and_unmapped():
    snap = HoldingsSnapshot(
        source_id="sec_13f:1", manager_name="SA LP", as_of=date(2026, 1, 1),
        rows=[HoldingRow(ticker="CLSK", side="LONG", weight=1.0)], unmapped_n=3)
    h = build_highlights([snap], max_age_days=30, today=date(2026, 6, 1))[0]
    assert h.stale is True and h.unmapped_n == 3
    assert "[stale]" in render_line(h) and "unmapped 3" in render_line(h)
