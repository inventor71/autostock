"""Aggregate metrics across all outcomes and rolling windows."""

from __future__ import annotations

import statistics

from src.agent.quality.metrics import (
    benchmark_excess,
    confidence_calibration,
    direction_hit_rate,
    exit_timing,
    mae,
    mfe,
    realized_rr,
    stop_quality,
    target_quality,
)
from src.agent.quality.models import DecisionOutcome


def _safe_stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "count": len(values),
    }


def _stop_distribution(outcomes: list[DecisionOutcome]) -> dict:
    quals = [stop_quality(o) for o in outcomes]
    return {
        "appropriate": quals.count("appropriate"),
        "noise_hit": quals.count("noise_hit"),
        "held": quals.count("held"),
        "n/a": quals.count("n/a"),
        "total": len(quals),
    }


def _target_stats(outcomes: list[DecisionOutcome]) -> dict:
    tqs = [target_quality(o) for o in outcomes]
    reached = [t for t in tqs if t["reached"]]
    days = [t["days_to_reach"] for t in reached if t["days_to_reach"] is not None]
    return {
        "reached_count": len(reached),
        "total": len(tqs),
        "reach_rate": len(reached) / len(tqs) if tqs else 0.0,
        "avg_days_to_reach": statistics.mean(days) if days else None,
    }


def summary(
    outcomes: list[DecisionOutcome],
    spy_path: list[dict] | None = None,
    qqq_path: list[dict] | None = None,
) -> dict:
    """Full-period summary across all outcomes."""
    mae_vals = [v for o in outcomes if (v := mae(o)) is not None]
    mfe_vals = [v for o in outcomes if (v := mfe(o)) is not None]
    rr_vals = [v for o in outcomes if (v := realized_rr(o)) is not None]
    et_vals = [v for o in outcomes if (v := exit_timing(o)) is not None]

    bench_excess_spy = []
    bench_excess_qqq = []
    for o in outcomes:
        be = benchmark_excess(o, spy_path, qqq_path)
        if be["vs_spy"] is not None:
            bench_excess_spy.append(be["vs_spy"])
        if be["vs_qqq"] is not None:
            bench_excess_qqq.append(be["vs_qqq"])

    return {
        "direction_hit_rate": direction_hit_rate(outcomes),
        "mae": _safe_stats(mae_vals),
        "mfe": _safe_stats(mfe_vals),
        "stop_quality": _stop_distribution(outcomes),
        "target_quality": _target_stats(outcomes),
        "confidence_calibration": confidence_calibration(outcomes),
        "realized_rr": _safe_stats(rr_vals),
        "exit_timing": _safe_stats(et_vals),
        "benchmark_excess_spy": _safe_stats(bench_excess_spy),
        "benchmark_excess_qqq": _safe_stats(bench_excess_qqq),
        "total_outcomes": len(outcomes),
    }


def rolling(
    outcomes: list[DecisionOutcome],
    window: int = 20,
    spy_path: list[dict] | None = None,
    qqq_path: list[dict] | None = None,
) -> list[dict]:
    """Rolling window summaries. Each entry covers outcomes[i:i+window]."""
    if len(outcomes) < window:
        return []
    results = []
    for i in range(len(outcomes) - window + 1):
        chunk = outcomes[i: i + window]
        s = summary(chunk, spy_path, qqq_path)
        s["window_start"] = i
        s["window_end"] = i + window - 1
        results.append(s)
    return results
