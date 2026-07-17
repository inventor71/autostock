"""F97 — agent-vs-SPY performance headline (compute_performance).

Example-based tests pin known scenarios (PBT-10); property-based tests verify the
scale/consistency/robustness invariants across generated equity+SPY series.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.logs.performance import compute_performance


def _rec(date, equity, spy=None):
    r = {"date": date, "equity": equity}
    if spy is not None:
        r["benchmark"] = {"SPY": spy, "QQQ": 700.0, "VIX": 16.0}
    return r


# --------------------------------------------------------------------------- #
# Example-based (PBT-10: pin the headline for concrete, business-critical cases)
# --------------------------------------------------------------------------- #
class TestComputePerformanceExamples:
    def test_agent_beats_spy(self):
        recs = [_rec("2026-05-28", 100.0, 750.0), _rec("2026-05-29", 110.0, 765.0)]
        perf = compute_performance(recs)
        assert perf["since_date"] == "2026-05-28"
        assert perf["days"] == 2
        assert perf["agent_return_pct"] == 10.0      # 100 -> 110
        assert perf["spy_return_pct"] == 2.0         # 750 -> 765
        assert perf["alpha_pct"] == 8.0              # 10 - 2
        # only two points, so today's delta == cumulative here
        assert perf["agent_day_pct"] == 10.0
        assert perf["spy_day_pct"] == 2.0
        assert perf["day_alpha_pct"] == 8.0

    def test_agent_trails_spy_negative_alpha(self):
        recs = [_rec("2026-05-28", 100000.0, 750.0), _rec("2026-07-11", 100100.0, 755.0)]
        perf = compute_performance(recs)
        assert perf["agent_return_pct"] == 0.1       # +0.10%
        assert perf["spy_return_pct"] == 0.67        # +0.67%
        assert perf["alpha_pct"] == -0.57            # trailing the index

    def test_baseline_skips_lines_without_spy(self):
        # Mirrors the real equity.jsonl: first line has no benchmark.
        recs = [
            _rec("2026-05-27", 100065.7),            # no SPY -> skipped, NOT the baseline
            _rec("2026-05-28", 100000.0, 750.0),     # baseline
            _rec("2026-05-29", 101000.0, 750.0),
        ]
        perf = compute_performance(recs)
        assert perf["since_date"] == "2026-05-28"
        assert perf["days"] == 2
        assert perf["agent_return_pct"] == 1.0
        assert perf["spy_return_pct"] == 0.0

    def test_today_delta_uses_last_two(self):
        recs = [
            _rec("2026-05-28", 100.0, 750.0),
            _rec("2026-05-29", 120.0, 750.0),
            _rec("2026-05-30", 132.0, 780.0),        # +10% agent day, +4% spy day
        ]
        perf = compute_performance(recs)
        assert perf["agent_day_pct"] == 10.0
        assert perf["spy_day_pct"] == 4.0
        assert perf["day_alpha_pct"] == 6.0

    def test_single_usable_record_zero_return_no_day(self):
        perf = compute_performance([_rec("2026-05-28", 100.0, 750.0)])
        assert perf["days"] == 1
        assert perf["agent_return_pct"] == 0.0
        assert perf["spy_return_pct"] == 0.0
        assert perf["alpha_pct"] == 0.0
        assert perf["agent_day_pct"] is None
        assert perf["day_alpha_pct"] is None

    def test_no_usable_records_returns_none(self):
        assert compute_performance([]) is None
        assert compute_performance([_rec("2026-05-27", 100.0)]) is None          # no SPY at all
        assert compute_performance([_rec("2026-05-27", 0.0, 750.0)]) is None      # equity <= 0

    def test_ignores_malformed_records(self):
        recs = [
            "not a dict",
            {"equity": "oops", "benchmark": {"SPY": 750.0}},   # non-numeric equity
            _rec("2026-05-28", 100.0, 750.0),
            {"equity": 110.0, "benchmark": {"SPY": 0}},        # SPY <= 0 -> skipped
            _rec("2026-05-29", 110.0, 765.0),
        ]
        perf = compute_performance(recs)
        assert perf["days"] == 2
        assert perf["agent_return_pct"] == 10.0
        assert perf["spy_return_pct"] == 2.0


# --------------------------------------------------------------------------- #
# Property-based (PBT-01..P6). Domain generators = positive-float series.
# --------------------------------------------------------------------------- #
_price = st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False)


@st.composite
def _equity_spy_series(draw, min_len=1, max_len=30):
    """A usable equity+SPY series (oldest first), all strictly positive."""
    n = draw(st.integers(min_value=min_len, max_value=max_len))
    eqs = draw(st.lists(_price, min_size=n, max_size=n))
    spys = draw(st.lists(_price, min_size=n, max_size=n))
    return [_rec(f"2026-06-{i + 1:02d}", eqs[i], spys[i]) for i in range(n)]


class TestComputePerformanceProperties:
    @given(recs=_equity_spy_series(), k=st.floats(min_value=0.01, max_value=1000.0))
    @settings(max_examples=100)
    def test_agent_return_scale_invariant(self, recs, k):
        """P1: scaling every equity by k>0 leaves agent_return_pct unchanged."""
        scaled = [{**r, "equity": r["equity"] * k} for r in recs]
        base = compute_performance(recs)
        assert compute_performance(scaled)["agent_return_pct"] == pytest.approx(
            base["agent_return_pct"], abs=1e-6
        )

    @given(recs=_equity_spy_series(), k=st.floats(min_value=0.01, max_value=1000.0))
    @settings(max_examples=100)
    def test_spy_return_scale_invariant(self, recs, k):
        """P1: scaling every SPY mark by k>0 leaves spy_return_pct unchanged."""
        scaled = [{**r, "benchmark": {**r["benchmark"], "SPY": r["benchmark"]["SPY"] * k}} for r in recs]
        base = compute_performance(recs)
        assert compute_performance(scaled)["spy_return_pct"] == pytest.approx(
            base["spy_return_pct"], abs=1e-6
        )

    @given(prices=st.lists(_price, min_size=2, max_size=30),
           c=st.floats(min_value=0.01, max_value=1000.0))
    @settings(max_examples=100)
    def test_zero_alpha_when_equity_tracks_spy(self, prices, c):
        """P2: if equity[i] == c * SPY[i], the agent exactly matches SPY -> alpha 0."""
        recs = [_rec(f"2026-06-{i + 1:02d}", c * p, p) for i, p in enumerate(prices)]
        perf = compute_performance(recs)
        assert perf["alpha_pct"] == pytest.approx(0.0, abs=1e-6)
        assert perf["agent_return_pct"] == pytest.approx(perf["spy_return_pct"], abs=1e-6)
        assert perf["day_alpha_pct"] == pytest.approx(0.0, abs=1e-6)

    @given(recs=_equity_spy_series())
    @settings(max_examples=100)
    def test_alpha_consistency(self, recs):
        """P4: alpha is exactly the (rounded) excess of agent over spy — likewise per-day.

        Both operands are already rounded to 2dp, so the excess is exact at 2dp;
        asserting the rounded identity avoids float-noise false negatives at the
        extreme magnitudes Hypothesis explores."""
        perf = compute_performance(recs)
        assert perf["alpha_pct"] == round(perf["agent_return_pct"] - perf["spy_return_pct"], 2)
        if perf["day_alpha_pct"] is not None:
            assert perf["day_alpha_pct"] == round(perf["agent_day_pct"] - perf["spy_day_pct"], 2)

    @given(recs=_equity_spy_series(),
           junk_date=st.text(max_size=8),
           junk_eq=st.floats(min_value=1.0, max_value=1e6))
    @settings(max_examples=100)
    def test_robust_to_inserted_spyless_record(self, recs, junk_date, junk_eq):
        """P5: inserting a record with no SPY mark anywhere does not change the result."""
        before = compute_performance(recs)
        polluted = [{"date": junk_date, "equity": junk_eq}] + recs + [{"date": junk_date, "equity": junk_eq}]
        assert compute_performance(polluted) == before

    @given(recs=_equity_spy_series())
    @settings(max_examples=100)
    def test_boundary_day_fields_presence(self, recs):
        """P6: day fields present iff >= 2 usable records."""
        perf = compute_performance(recs)
        if perf["days"] >= 2:
            assert perf["agent_day_pct"] is not None
        else:
            assert perf["agent_day_pct"] is None and perf["day_alpha_pct"] is None
