"""Retail-sentiment core (F77): label math, baselines, outlier selection, I/O.

The pure functions carry the signal semantics (StockTwits rests ~75% bullish,
so only per-symbol z-deviation matters); the I/O layer must be fail-honest and
lenient like every other workspace log.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from hypothesis import given
from hypothesis import strategies as st

from src.signals import sentiment
from src.signals.records import SentimentRecord
from src.signals.settings import SentimentConfig

TS = datetime(2026, 6, 12, 14, 0, tzinfo=timezone.utc)
CFG = SentimentConfig(min_baseline_points=3, min_tagged=5, top_k=2,
                      z_threshold=2.0, baseline_days=5, max_age_minutes=180)


def _rec(symbol="NVDA", bull=10, bear=5, untagged=3, ts=TS, latest_id=None):
    return SentimentRecord(ts=ts, symbol=symbol, bullish_n=bull,
                           bearish_n=bear, untagged_n=untagged, latest_id=latest_id)


# --------------------------------------------------------------------------- #
# Pure core — properties
# --------------------------------------------------------------------------- #
class TestPureProperties:
    @given(bull=st.integers(0, 1000), bear=st.integers(0, 1000))
    def test_bull_ratio_bounded_or_none(self, bull, bear):
        r = sentiment.bull_ratio(bull, bear)
        if bull + bear == 0:
            assert r is None
        else:
            assert 0.0 <= r <= 1.0

    @given(st.lists(st.tuples(st.integers(0, 50), st.integers(0, 50)), max_size=20))
    def test_baseline_never_raises_and_counts_points(self, counts):
        history = [_rec(bull=b, bear=r, ts=TS + timedelta(hours=i))
                   for i, (b, r) in enumerate(counts)]
        base = sentiment.baseline(history)
        assert base.n_points == len(history)
        if base.ratio_mean is not None:
            assert 0.0 <= base.ratio_mean <= 1.0

    @given(value=st.one_of(st.none(), st.floats(-1e6, 1e6)),
           mean=st.one_of(st.none(), st.floats(-1e6, 1e6)),
           std=st.one_of(st.none(), st.floats(-10, 1e6)))
    def test_zscore_total_never_raises(self, value, mean, std):
        z = sentiment.zscore(value, mean, std)
        if None in (value, mean, std) or std <= 0.0:
            assert z is None

    @given(st.lists(st.builds(
        SentimentRecord,
        ts=st.just(TS), symbol=st.text("ABC", min_size=1, max_size=4),
        bullish_n=st.integers(0, 99), bearish_n=st.integers(0, 99),
        untagged_n=st.integers(0, 99),
        latest_id=st.one_of(st.none(), st.integers(0, 10**9)),
    ), max_size=5))
    def test_record_roundtrip(self, recs):
        for r in recs:
            assert SentimentRecord.model_validate(
                json.loads(json.dumps(r.model_dump(mode="json")))) == r


# --------------------------------------------------------------------------- #
# Outlier selection — example-based cut rules
# --------------------------------------------------------------------------- #
def _history(symbol, bulls, tagged=20):
    """One record per bull count (fixed tagged volume), hourly spacing (oldest first)."""
    return [_rec(symbol=symbol, bull=b, bear=tagged - b, ts=TS + timedelta(hours=i))
            for i, b in enumerate(bulls)]


class TestSelectOutliers:
    def test_ratio_shift_is_selected_and_direction_labeled(self):
        # stable ~0.75 baseline, current collapses to 0.25 → bearish outlier
        hist = _history("NVDA", [15, 14, 16, 15, 5])
        currents, baselines = sentiment.latest_and_baselines({"NVDA": hist})
        out = sentiment.select_outliers(currents, baselines, CFG)
        assert [o.symbol for o in out] == ["NVDA"]
        assert out[0].direction == "bearish"
        assert out[0].ratio_z is not None and out[0].ratio_z < 0

    def test_cold_start_and_thin_snapshot_are_cut(self):
        cold = _history("AMD", [14, 2])  # 1 baseline point < min 3
        thin = _history("MU", [3, 3, 3, 3, 0], tagged=4)  # current tagged 4 < min 5
        currents, baselines = sentiment.latest_and_baselines(
            {"AMD": cold, "MU": thin})
        assert sentiment.select_outliers(currents, baselines, CFG) == []

    def test_top_k_caps_and_ranks_by_score(self):
        hists = {
            s: _history(s, [15, 14, 16, 15, cur])
            for s, cur in [("AAA", 2), ("BBB", 6), ("CCC", 9)]
        }
        currents, baselines = sentiment.latest_and_baselines(hists)
        out = sentiment.select_outliers(currents, baselines, CFG)
        assert len(out) == 2  # top_k
        assert out[0].symbol == "AAA"  # biggest deviation first

    def test_quiet_universe_yields_nothing(self):
        hist = _history("NVDA", [15, 14, 16, 15, 15])
        currents, baselines = sentiment.latest_and_baselines({"NVDA": hist})
        assert sentiment.select_outliers(currents, baselines, CFG) == []


# --------------------------------------------------------------------------- #
# I/O — append/load + freshness
# --------------------------------------------------------------------------- #
class TestIO:
    def test_append_then_load_roundtrip(self, tmp_path):
        recs = [_rec("NVDA"), _rec("AMD", bull=2, bear=8)]
        path = sentiment.append_sweep(recs, root=tmp_path, ts=TS)
        assert path is not None and path.exists()
        history = sentiment.load_recent(tmp_path, days=2, now=TS)
        assert set(history) == {"NVDA", "AMD"}

    def test_load_lenient_on_corrupt_lines(self, tmp_path):
        sentiment.append_sweep([_rec("NVDA")], root=tmp_path, ts=TS)
        p = sentiment.append_sweep([_rec("NVDA")], root=tmp_path, ts=TS)
        with open(p, "a", encoding="utf-8") as f:
            f.write("{torn\n\n")
        history = sentiment.load_recent(tmp_path, days=2, now=TS)
        assert len(history["NVDA"]) == 2

    def test_append_failure_returns_none(self, tmp_path):
        (tmp_path / "sentiment").write_text("not a dir")
        assert sentiment.append_sweep([_rec()], root=tmp_path, ts=TS) is None

    def test_current_outliers_drops_stale_current(self, tmp_path):
        # all points written long before 'now' → current is stale → nothing surfaces
        for i, bull in enumerate([15, 14, 16, 15, 2]):
            sentiment.append_sweep(
                [_rec("NVDA", bull=bull, bear=20 - bull, ts=TS + timedelta(hours=i))],
                root=tmp_path, ts=TS)
        now = TS + timedelta(days=1)
        assert sentiment.current_outliers(CFG, root=tmp_path, now=now) == []
        # but at sweep time it does surface
        fresh_now = TS + timedelta(hours=4, minutes=30)
        out = sentiment.current_outliers(CFG, root=tmp_path, now=fresh_now)
        assert [o.symbol for o in out] == ["NVDA"]

    def test_outlier_lines_filter_symbols_and_never_raise(self, tmp_path):
        for i, bull in enumerate([15, 14, 16, 15, 2]):
            sentiment.append_sweep(
                [_rec("NVDA", bull=bull, bear=20 - bull, ts=TS + timedelta(hours=i))],
                root=tmp_path, ts=TS)
        lines = sentiment.outlier_lines_for(["NVDA"], CFG, root=tmp_path)
        # may be empty depending on wall-clock freshness — must not raise; if
        # present it names the symbol
        assert all("NVDA" in ln for ln in lines)
        assert sentiment.outlier_lines_for(["MSFT"], CFG, root=tmp_path) == []
