"""Pure metric calculation functions. No side effects, no I/O."""

from __future__ import annotations

import math

from src.agent.quality.models import DecisionOutcome


def _direction(outcome: DecisionOutcome) -> int:
    return -1 if outcome.decision.action in ("SELL_SHORT", "BUY_TO_COVER") else 1


def direction_hit_rate(outcomes: list[DecisionOutcome], horizon: int | None = None) -> dict:
    """Mature entry forecasts, measured over their collected grading window."""
    entries = [o for o in outcomes if o.decision.action in ("BUY", "SELL_SHORT")
               and o.mature and len(o.price_path) > 1 and o.price_path[0].close > 0]
    if not entries:
        return {"total": 0, "hits": 0, "rate": 0.0}
    hits = 0
    for o in entries:
        entry = o.price_path[0].close
        end_idx = min(horizon, len(o.price_path) - 1) if horizon is not None else -1
        exit_price = o.price_path[end_idx].close
        if _direction(o) * (exit_price - entry) > 0:
            hits += 1
    return {"total": len(entries), "hits": hits, "rate": hits / len(entries)}


def mae(outcome: DecisionOutcome) -> float | None:
    """Maximum Adverse Excursion: worst intra-holding drawdown from entry."""
    if not outcome.price_path or outcome.round_trip is None:
        return None
    entry = outcome.round_trip.entry_price
    if entry <= 0:
        return None
    if _direction(outcome) < 0:
        return max(0.0, (max(bar.high for bar in outcome.price_path) - entry) / entry)
    return max(0.0, (entry - min(bar.low for bar in outcome.price_path)) / entry)


def mfe(outcome: DecisionOutcome) -> float | None:
    """Maximum Favorable Excursion: best intra-holding gain from entry."""
    if not outcome.price_path or outcome.round_trip is None:
        return None
    entry = outcome.round_trip.entry_price
    if entry <= 0:
        return None
    if _direction(outcome) < 0:
        return max(0.0, (entry - min(bar.low for bar in outcome.price_path)) / entry)
    return max(0.0, (max(bar.high for bar in outcome.price_path) - entry) / entry)


def stop_quality(outcome: DecisionOutcome, post_trigger_days: int = 5) -> str:
    """Evaluate whether the stop was noise or appropriate."""
    d = outcome.decision
    if d.stop is None:
        return "n/a"
    if not outcome.price_path:
        return "n/a"

    short = _direction(outcome) < 0
    def touched(bar):
        return bar.high >= d.stop if short else bar.low <= d.stop

    stop_triggered = any(touched(bar) for bar in outcome.price_path)
    if not stop_triggered:
        near_stop = any(bar.high >= d.stop * 0.98 if short else bar.low <= d.stop * 1.02
                        for bar in outcome.price_path)
        return "held" if near_stop else "n/a"

    trigger_idx = next(
        i for i, bar in enumerate(outcome.price_path) if touched(bar)
    )
    post = outcome.price_path[trigger_idx + 1: trigger_idx + 1 + post_trigger_days]
    if not post:
        return "appropriate"
    recovered = any(bar.close < d.stop * 0.97 if short else bar.close > d.stop * 1.03
                    for bar in post)
    return "noise_hit" if recovered else "appropriate"


def target_quality(outcome: DecisionOutcome) -> dict:
    """Whether target was reached and how long it took."""
    d = outcome.decision
    if d.target is None or not outcome.price_path:
        return {"reached": False, "days_to_reach": None}
    for i, bar in enumerate(outcome.price_path):
        if (bar.low <= d.target if _direction(outcome) < 0 else bar.high >= d.target):
            return {"reached": True, "days_to_reach": i}
    return {"reached": False, "days_to_reach": None}


def confidence_calibration(outcomes: list[DecisionOutcome], horizon: int | None = None) -> dict:
    """Observed direction by stated confidence, not a calibrated win probability."""
    buckets = {
        "0.0-0.49": {"count": 0, "hits": 0},
        "0.5-0.7": {"count": 0, "hits": 0},
        "0.7-0.9": {"count": 0, "hits": 0},
        "0.9-1.0": {"count": 0, "hits": 0},
    }

    def _bucket(c: float) -> str | None:
        if not math.isfinite(c) or not 0 <= c <= 1:
            return None
        if c < 0.5:
            return "0.0-0.49"
        if c <= 0.7:
            return "0.5-0.7"
        if c <= 0.9:
            return "0.7-0.9"
        return "0.9-1.0"

    for o in outcomes:
        if (o.decision.action not in ("BUY", "SELL_SHORT") or not o.mature
                or len(o.price_path) <= 1 or o.price_path[0].close <= 0):
            continue
        c = o.decision.confidence
        if c is None:
            continue
        b = _bucket(c)
        if b is None:
            continue
        buckets[b]["count"] += 1
        entry = o.price_path[0].close
        end_idx = min(horizon, len(o.price_path) - 1) if horizon is not None else -1
        if _direction(o) * (o.price_path[end_idx].close - entry) > 0:
            buckets[b]["hits"] += 1

    result = {}
    for k, v in buckets.items():
        result[k] = {
            "count": v["count"],
            "hits": v["hits"],
            "rate": v["hits"] / v["count"] if v["count"] > 0 else 0.0,
        }
    return result


def realized_rr(outcome: DecisionOutcome) -> float | None:
    """Realized return in units of initial risk, using the actual fill price."""
    d = outcome.decision
    rt = outcome.round_trip
    if d.stop is None or rt is None:
        return None
    planned_risk = _direction(outcome) * (rt.entry_price - d.stop)
    if planned_risk <= 0:
        return None
    actual_pnl = _direction(outcome) * (rt.exit_price - rt.entry_price)
    return actual_pnl / planned_risk


def benchmark_excess(
    outcome: DecisionOutcome,
    spy_path: list[dict] | None,
    qqq_path: list[dict] | None,
) -> dict:
    """Directional entry forecast vs benchmarks on exactly the same dates.

    This close-to-close proxy excludes execution costs and is not realized P&L.
    Missing benchmark endpoints are unknown, never a mismatched-period return.
    """
    result: dict[str, float | None] = {"vs_spy": None, "vs_qqq": None}
    if (outcome.decision.action not in ("BUY", "SELL_SHORT")
            or len(outcome.price_path) < 2 or outcome.price_path[0].close <= 0):
        return result
    stock_return = _direction(outcome) * (
        (outcome.price_path[-1].close / outcome.price_path[0].close) - 1
    )
    start_date = str(outcome.price_path[0].date)[:10]
    end_date = str(outcome.price_path[-1].date)[:10]

    for bench_name, bench_path in [("vs_spy", spy_path), ("vs_qqq", qqq_path)]:
        if bench_path and len(bench_path) >= 2:
            dated = {
                str(bar.date if hasattr(bar, "date") else bar.get("date", ""))[:10]:
                (bar.close if hasattr(bar, "close") else bar.get("close"))
                for bar in bench_path
            }
            start_close, end_close = dated.get(start_date), dated.get(end_date)
            if (start_close is None or end_close is None
                    or not math.isfinite(start_close) or not math.isfinite(end_close)
                    or start_close <= 0 or end_close <= 0):
                continue
            bench_return = (end_close / start_close) - 1
            result[bench_name] = stock_return - bench_return
    return result


def exit_timing(outcome: DecisionOutcome, horizon: int = 5) -> float | None:
    """Exit opportunity cost, with direction appropriate to the closed position.
    Positive = left money on the table; negative = good timing."""
    if outcome.decision.action not in ("SELL", "BUY_TO_COVER"):
        return None
    if not outcome.price_path or len(outcome.price_path) < 2:
        return None
    exit_price = outcome.price_path[0].close
    end_idx = min(horizon, len(outcome.price_path) - 1)
    post_price = outcome.price_path[end_idx].close
    if exit_price <= 0:
        return None
    return _direction(outcome) * (post_price - exit_price) / exit_price
