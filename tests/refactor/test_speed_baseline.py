"""R2 speed-review characterization tests.

Freeze the observable output of the backtest engine + optimizer against a golden
snapshot captured from the pre-refactor baseline (see scenarios.py + golden/
baseline.json). Every R2 speed change (C-1a/C-1b/C-2) must keep these green; a
red here means the change altered behavior (a T3 signal), not a pure speedup.

Regenerate the golden ONLY intentionally:
    python -c "import json,sys; sys.path.insert(0,'.'); \
        from tests.refactor import scenarios as s; \
        json.dump({'engine':s.run_engine(),'optimizer':s.run_optimizer()}, \
        open('tests/refactor/golden/baseline.json','w'), indent=2, sort_keys=True)"
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.refactor import scenarios

GOLDEN = json.loads((Path(__file__).parent / "golden" / "baseline.json").read_text())

# Exact for everything the value-preserving changes (C-1a/C-2/C-3p/C-4) touch.
# C-1b (incremental indicators) is expected bit-identical for rolling-window
# indicators; this tolerance only catches genuine ewm float-accumulation drift,
# which (per the redesign) must be reported to the user before acceptance.
REL = 1e-12


def _approx(value):
    return pytest.approx(value, rel=REL, abs=1e-9)


def test_engine_result_matches_golden():
    got = scenarios.run_engine()
    exp = GOLDEN["engine"]

    assert got["total_trades"] == exp["total_trades"]
    assert len(got["equity_curve"]) == len(exp["equity_curve"])
    assert got["equity_curve"] == _approx(exp["equity_curve"])
    for key in ("final_capital", "total_return_pct", "sharpe_ratio",
                "max_drawdown_pct", "win_rate", "profit_factor"):
        assert got[key] == _approx(exp[key]), key

    assert len(got["fills"]) == len(exp["fills"])
    for g, e in zip(got["fills"], exp["fills"]):
        assert g["symbol"] == e["symbol"]
        assert g["side"] == e["side"]
        assert g["qty"] == _approx(e["qty"])
        assert g["price"] == _approx(e["price"])


def test_ma_fast_path_matches_generate_signal_per_bar():
    """C-1b contract: precompute + generate_signal_at(i) must equal the default
    generate_signal(bars[:i+1]) at every bar (the equivalence the speedup rests on)."""
    from src.core.exceptions import InsufficientDataError
    from src.strategy.technical.ma_crossover import MovingAverageCrossover

    bars = scenarios.make_bars(120)
    fast = MovingAverageCrossover(params={"fast_period": 10, "slow_period": 30})
    fast.precompute("TEST", bars)
    slow = MovingAverageCrossover(params={"fast_period": 10, "slow_period": 30})

    for i in range(len(bars)):
        try:
            ref = slow.generate_signal("TEST", bars.iloc[: i + 1])
            ref_err = None
        except InsufficientDataError:
            ref, ref_err = None, True
        try:
            got = fast.generate_signal_at("TEST", bars, i)
            got_err = None
        except InsufficientDataError:
            got, got_err = None, True

        assert (ref_err is None) == (got_err is None), f"guard mismatch at i={i}"
        if ref is not None:
            assert got.signal == ref.signal, i
            assert got.confidence == pytest.approx(ref.confidence), i
            assert got.metadata["fast_ma"] == pytest.approx(ref.metadata["fast_ma"]), i
            assert got.metadata["slow_ma"] == pytest.approx(ref.metadata["slow_ma"]), i


def test_optimizer_result_matches_golden():
    got = scenarios.run_optimizer()
    exp = GOLDEN["optimizer"]

    # first-max-wins best selection must be deterministic across parallelization.
    assert got["best_params"] == exp["best_params"]
    assert got["best_metric"] == _approx(exp["best_metric"])

    # all_results set AND order preserved.
    assert len(got["all_results"]) == len(exp["all_results"])
    for g, e in zip(got["all_results"], exp["all_results"]):
        assert g["params"] == e["params"]
        assert g["metric_value"] == _approx(e["metric_value"])
