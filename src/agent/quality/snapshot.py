"""Compact quality summary for EOD review prompt injection."""

from __future__ import annotations

from src.agent.quality.aggregate import summary
from src.agent.quality.models import DecisionOutcome


def quality_snapshot(
    outcomes: list[DecisionOutcome],
    min_decisions: int = 5,
) -> str | None:
    """One-paragraph quality summary. Returns None if too few decisions."""
    if len(outcomes) < min_decisions:
        return None

    s = summary(outcomes)
    hr = s["direction_hit_rate"]
    mae_s = s["mae"]
    mfe_s = s["mfe"]
    sq = s["stop_quality"]
    cal = s["confidence_calibration"]
    rr = s["realized_rr"]

    lines = [
        f"Decision Quality ({s['total_outcomes']} decisions analyzed):",
        f"  Direction hit rate (BUY): {hr['hits']}/{hr['total']} = {hr['rate']:.0%}",
    ]
    if mae_s["count"] > 0:
        lines.append(f"  Avg MAE: {mae_s['mean']:.1%}, Avg MFE: {mfe_s['mean']:.1%}")
    if sq["total"] > sq["n/a"]:
        scored = sq["total"] - sq["n/a"]
        noise = sq["noise_hit"]
        lines.append(
            f"  Stop quality: {sq['appropriate']} appropriate, "
            f"{noise} noise hits out of {scored} scored"
        )
    if rr["count"] > 0:
        lines.append(f"  Avg realized R:R: {rr['mean']:.2f}")

    scored_cal = {k: v for k, v in cal.items() if v["count"] > 0}
    if scored_cal:
        cal_parts = [f"{k}: {v['rate']:.0%} ({v['count']})" for k, v in scored_cal.items()]
        lines.append(f"  Confidence calibration: {', '.join(cal_parts)}")

    return "\n".join(lines)
