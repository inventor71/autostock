"""Tests for the P0 intraday pattern-detection modules (features/store/collector/analysis).

All network-free: synthetic bars and an in-memory provider stub.
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.core.types import TimeFrame
from src.data.intraday.analysis import (
    DEFAULT_HYPOTHESES,
    analyze,
    to_markdown,
    with_derived,
)
from src.data.intraday.collector import collect, features_for_symbol, sessionize
from src.data.intraday.features import FEATURE_COLUMNS, compute_session_features
from src.data.intraday.store import IntradayFeatureStore


def _session(start="2026-01-05 09:30") -> pd.DataFrame:
    """A hand-crafted 8-bar 5-minute session with a known shape.

    Low at 09:40 (recover after), close near the high, open->close up.
    """
    idx = pd.date_range(start, periods=8, freq="5min")
    opens = [100, 99, 98, 99, 100, 101, 102, 103]
    closes = [99, 98, 99, 100, 101, 102, 103, 104]
    highs = [100.5, 99.5, 99.5, 100.5, 101.5, 102.5, 103.5, 104.5]
    lows = [99, 97.5, 97, 98.5, 99.5, 100.5, 101.5, 102.5]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000] * 8},
        index=idx,
    )


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
class TestFeatures:
    def test_known_session(self):
        f = compute_session_features(
            _session(), symbol="aapl", session_date=date(2026, 1, 5), prev_close=105.0
        )
        assert f["symbol"] == "AAPL"
        assert f["date"] == "2026-01-05"
        assert f["open"] == 100.0 and f["close"] == 104.0
        assert f["high"] == 104.5 and f["low"] == 97.0
        assert f["gap_pct"] == pytest.approx(100 / 105 - 1, abs=1e-6)
        assert f["oc_ret"] == pytest.approx(0.04, abs=1e-6)
        assert f["or_ret"] == pytest.approx(0.02, abs=1e-6)  # close of 09:55 bar = 102
        assert f["or_range_pct"] == pytest.approx((102.5 - 97) / 100, abs=1e-6)
        assert f["last30_ret"] == pytest.approx(104 / 98 - 1, abs=1e-6)  # ref = 09:35 close
        assert f["hi_t_min"] == 35  # high at last bar 10:05
        assert f["lo_t_min"] == 10  # low at 09:40
        assert f["max_drawup_pct"] == pytest.approx(0.045, abs=1e-6)
        assert f["max_drawdown_pct"] == pytest.approx(-0.03, abs=1e-6)
        assert f["close_loc"] == pytest.approx((104 - 97) / (104.5 - 97), abs=1e-6)
        assert set(f.keys()) == set(FEATURE_COLUMNS)

    def test_no_prev_close_means_no_gap(self):
        f = compute_session_features(
            _session(), symbol="X", session_date=date(2026, 1, 5), prev_close=None
        )
        assert f["gap_pct"] is None
        assert f["prev_close"] is None

    def test_empty_raises(self):
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        with pytest.raises(ValueError):
            compute_session_features(empty, symbol="X", session_date=date(2026, 1, 5), prev_close=1)

    @settings(max_examples=60)
    @given(
        rows=st.lists(
            st.tuples(
                st.floats(1.0, 1000.0),
                st.floats(1.0, 1000.0),
                st.floats(0.0, 5.0),
                st.floats(0.0, 5.0),
            ),
            min_size=2,
            max_size=20,
        )
    )
    def test_invariants(self, rows):
        idx = pd.date_range("2026-01-05 09:30", periods=len(rows), freq="5min")
        data = []
        for o, c, up, dn in rows:
            hi = max(o, c) + up
            lo = max(0.01, min(o, c) - dn)
            data.append((o, hi, lo, c, 1000))
        df = pd.DataFrame(data, index=idx, columns=["open", "high", "low", "close", "volume"])
        f = compute_session_features(df, symbol="X", session_date=date(2026, 1, 5), prev_close=None)
        assert 0.0 <= f["close_loc"] <= 1.0
        assert f["max_drawup_pct"] >= 0 >= f["max_drawdown_pct"]
        assert f["high"] >= f["low"]


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
def _rec(d: str, symbol: str, oc: float, gap: float = 0.0) -> dict:
    rec = {col: None for col in FEATURE_COLUMNS}
    rec.update({"date": d, "symbol": symbol, "oc_ret": oc, "gap_pct": gap, "or_ret": 0.0})
    return rec


class TestStore:
    def test_roundtrip_and_idempotency(self, tmp_path):
        store = IntradayFeatureStore(root=tmp_path)
        store.upsert([_rec("2026-01-05", "AAPL", 0.01), _rec("2026-01-06", "AAPL", 0.02)])
        # Re-upserting the same date must not duplicate; last write wins.
        store.upsert([_rec("2026-01-05", "AAPL", 0.99)])
        df = store.read(["AAPL"])
        assert list(df["date"]) == ["2026-01-05", "2026-01-06"]
        assert df.loc[df["date"] == "2026-01-05", "oc_ret"].iloc[0] == 0.99

    def test_read_filters_and_multi_symbol(self, tmp_path):
        store = IntradayFeatureStore(root=tmp_path)
        store.upsert([_rec("2026-01-05", "AAPL", 0.01), _rec("2026-01-07", "AAPL", 0.03)])
        store.upsert([_rec("2026-01-06", "MSFT", 0.05)])
        assert store.symbols() == ["AAPL", "MSFT"]
        rng = store.read(start=date(2026, 1, 6), end=date(2026, 1, 6))
        assert list(rng["symbol"]) == ["MSFT"]

    def test_read_empty(self, tmp_path):
        df = IntradayFeatureStore(root=tmp_path / "nope").read()
        assert df.empty and list(df.columns) == FEATURE_COLUMNS

    def test_persists_as_parquet_not_csv(self, tmp_path):
        store = IntradayFeatureStore(root=tmp_path)
        store.upsert([_rec("2026-01-05", "AAPL", 0.01)])
        assert (tmp_path / "AAPL.parquet").exists()
        assert not list(tmp_path.glob("*.csv"))


class TestStoreLegacyMigration:
    """Legacy CSV files (the original backend) migrate to Parquet once, lazily."""

    def _write_legacy_csv(self, tmp_path, symbol, recs):
        tmp_path.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(recs).reindex(columns=FEATURE_COLUMNS)
        df.to_csv(tmp_path / f"{symbol}.csv", index=False)

    def test_read_migrates_legacy_csv(self, tmp_path):
        self._write_legacy_csv(
            tmp_path, "AAPL", [_rec("2026-01-05", "AAPL", 0.01), _rec("2026-01-06", "AAPL", 0.02)]
        )
        store = IntradayFeatureStore(root=tmp_path)
        df = store.read(["AAPL"])
        assert list(df["date"]) == ["2026-01-05", "2026-01-06"]
        # CSV converted to Parquet, source preserved (not silently deleted), not re-read.
        assert (tmp_path / "AAPL.parquet").exists()
        assert not (tmp_path / "AAPL.csv").exists()
        assert (tmp_path / "AAPL.csv.migrated").exists()

    def test_symbols_sees_migrated_and_native(self, tmp_path):
        self._write_legacy_csv(tmp_path, "AAPL", [_rec("2026-01-05", "AAPL", 0.01)])
        store = IntradayFeatureStore(root=tmp_path)
        store.upsert([_rec("2026-01-06", "MSFT", 0.05)])  # native parquet
        assert store.symbols() == ["AAPL", "MSFT"]

    def test_upsert_after_migration_merges(self, tmp_path):
        self._write_legacy_csv(tmp_path, "AAPL", [_rec("2026-01-05", "AAPL", 0.01)])
        store = IntradayFeatureStore(root=tmp_path)
        store.upsert([_rec("2026-01-06", "AAPL", 0.02)])
        assert list(store.read(["AAPL"])["date"]) == ["2026-01-05", "2026-01-06"]
        assert not (tmp_path / "AAPL.csv").exists()


# --------------------------------------------------------------------------- #
# Store — property-based (PBT extension: round-trip + idempotence)
# --------------------------------------------------------------------------- #
_PBT_SYMBOLS = st.sampled_from(["AAPL", "MSFT", "TSLA", "NVDA"])
_PBT_DATES = st.dates(date(2024, 1, 1), date(2026, 12, 31)).map(lambda d: d.isoformat())
_PBT_NUMERIC = st.one_of(
    st.none(),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)


@st.composite
def _pbt_record(draw):
    rec = {col: draw(_PBT_NUMERIC) for col in FEATURE_COLUMNS}
    rec["date"] = draw(_PBT_DATES)
    rec["symbol"] = draw(_PBT_SYMBOLS)
    return rec


class TestStoreProperties:
    @settings(max_examples=50)
    @given(records=st.lists(_pbt_record(), max_size=25))
    def test_roundtrip_preserves_values(self, records):
        """upsert → read returns every (date,symbol) row with values/types intact.

        Round-trip property (serialize → deserialize = identity), with last-write-wins
        collapsing duplicate (date,symbol) keys exactly as the store contract promises.
        """
        with tempfile.TemporaryDirectory() as root:  # fresh per example (no state leak)
            store = IntradayFeatureStore(root=root)
            store.upsert(records)

            expected = {(r["date"], r["symbol"]): r for r in records}  # last write wins
            df = store.read()
            assert len(df) == len(expected)
            assert list(df.columns) == FEATURE_COLUMNS
            for row in df.to_dict("records"):
                orig = expected[(row["date"], row["symbol"])]
                for col in FEATURE_COLUMNS:
                    ov, rv = orig[col], row[col]
                    if ov is None:
                        assert pd.isna(rv), f"{col}: expected NaN, got {rv!r}"
                    else:
                        assert rv == ov, f"{col}: {rv!r} != {ov!r}"

    @settings(max_examples=50)
    @given(records=st.lists(_pbt_record(), max_size=25))
    def test_idempotent_reupsert(self, records):
        """Re-applying the same upsert leaves the store byte-for-byte equivalent."""
        with tempfile.TemporaryDirectory() as root:  # fresh per example (no state leak)
            store = IntradayFeatureStore(root=root)
            store.upsert(records)
            first = store.read()
            store.upsert(records)
            second = store.read()
            assert first.equals(second)


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #
class _StubProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self._frames = frames
        self.calls: list[dict] = []

    def get_bars(self, symbol, timeframe=TimeFrame.MINUTE_5, start=None, end=None, limit=100):
        self.calls.append({"symbol": symbol, "start": start, "end": end, "limit": limit})
        if symbol not in self._frames:
            raise RuntimeError("no data")
        return self._frames[symbol]


class TestCollector:
    def test_sessionize_splits_by_day(self):
        s1 = _session("2026-01-05 09:30")
        s2 = _session("2026-01-06 09:30")
        sessions = sessionize(pd.concat([s2, s1]))  # out of order on purpose
        assert [d.isoformat() for d, _ in sessions] == ["2026-01-05", "2026-01-06"]

    def test_features_for_symbol_chains_prev_close(self):
        bars = pd.concat([_session("2026-01-05 09:30"), _session("2026-01-06 09:30")])
        recs = features_for_symbol("AAPL", bars)
        assert len(recs) == 2
        assert recs[0]["gap_pct"] is None  # first session has no prior close
        # Second session's prev_close is the first session's close (104).
        assert recs[1]["prev_close"] == 104.0

    def test_collect_persists_and_handles_failure(self, tmp_path):
        provider = _StubProvider({"AAPL": _session("2026-01-05 09:30")})
        store = IntradayFeatureStore(root=tmp_path)
        summary = collect(provider, ["AAPL", "BADSYM"], store)
        assert summary == {"AAPL": 1, "BADSYM": 0}
        assert len(store.read(["AAPL"])) == 1

    def test_collect_limit_mode(self, tmp_path):
        provider = _StubProvider({"AAPL": _session("2026-01-05 09:30")})
        collect(provider, ["AAPL"], IntradayFeatureStore(root=tmp_path), limit=500)
        call = provider.calls[-1]
        assert call["limit"] == 500 and call["start"] is None and call["end"] is None

    def test_collect_range_mode_passes_dates_and_drops_limit(self, tmp_path):
        provider = _StubProvider({"AAPL": _session("2026-01-05 09:30")})
        start, end = datetime(2022, 1, 1), datetime(2024, 1, 1)
        collect(
            provider, ["AAPL"], IntradayFeatureStore(root=tmp_path), start=start, end=end
        )
        call = provider.calls[-1]
        assert call["start"] == start and call["end"] == end and call["limit"] is None


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _analysis_df(gap_down_n: int = 8, normal_n: int = 12) -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2026-01-05", periods=gap_down_n + normal_n, freq="D")
    di = 0
    for _ in range(gap_down_n):
        rows.append({"date": dates[di].date().isoformat(), "symbol": "AAPL",
                     "gap_pct": -0.03, "or_ret": 0.0, "oc_ret": 0.02})
        di += 1
    for _ in range(normal_n):
        rows.append({"date": dates[di].date().isoformat(), "symbol": "AAPL",
                     "gap_pct": 0.0, "or_ret": 0.0, "oc_ret": 0.0})
        di += 1
    return pd.DataFrame(rows)


class TestAnalysis:
    def test_with_derived_rod_ret(self):
        df = with_derived(pd.DataFrame({"oc_ret": [0.02], "or_ret": [0.0]}))
        assert df["rod_ret"].iloc[0] == pytest.approx(0.02)

    def test_detects_injected_pattern(self):
        report = analyze(_analysis_df(), windows=4)
        byname = {h["name"]: h for h in report["hypotheses"]}
        gd = byname["gap_down_reversion"]["summary"]
        assert gd["n"] == 8
        assert gd["hit_rate"] == 1.0
        assert gd["mean_excess"] > 0
        assert gd["direction_ok"] is True
        # Rolling stability splits the 8 qualifying rows into 4 windows.
        assert len(byname["gap_down_reversion"]["rolling"]) == 4

    def test_no_qualifying_sessions(self):
        # No gap-ups in this df -> gap_up_fade has zero qualifying rows.
        report = analyze(_analysis_df())
        byname = {h["name"]: h for h in report["hypotheses"]}
        assert byname["gap_up_fade"]["summary"] == {"n": 0}

    def test_flat_outcome_has_no_edge(self):
        flat = pd.DataFrame(
            {"date": ["2026-01-0%d" % i for i in range(1, 9)], "symbol": "X",
             "gap_pct": [-0.03] * 8, "or_ret": 0.0, "oc_ret": 0.0}
        )
        report = analyze(flat)
        gd = {h["name"]: h for h in report["hypotheses"]}["gap_down_reversion"]["summary"]
        assert gd["mean_excess"] == 0.0
        assert gd["hit_rate"] == 0.0  # sign(0) != +1

    def test_markdown_renders(self):
        md = to_markdown(analyze(_analysis_df()))
        assert "Intraday pattern-existence report" in md
        for h in DEFAULT_HYPOTHESES:
            assert h.name in md
