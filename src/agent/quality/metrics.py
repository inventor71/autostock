"""Pure metric calculation functions. No side effects, no I/O."""

from __future__ import annotations

from src.agent.quality.models import DecisionOutcome


def direction_hit_rate(outcomes: list[DecisionOutcome], horizon: int = 5) -> dict:
    """BUY-only: fraction of BUY decisions where price rose within N days."""
    buys = [o for o in outcomes if o.decision.action == "BUY" and len(o.price_path) > 1]
    if not buys:
        return {"total": 0, "hits": 0, "rate": 0.0}
    hits = 0
    for o in buys:
        entry = o.price_path[0].close
        end_idx = min(horizon, len(o.price_path) - 1)
        exit_price = o.price_path[end_idx].close
        if exit_price > entry:
            hits += 1
    return {"total": len(buys), "hits": hits, "rate": hits / len(buys)}


def mae(outcome: DecisionOutcome) -> float | None:
    """Maximum Adverse Excursion: worst intra-holding drawdown from entry."""
    if not outcome.price_path or outcome.round_trip is None:
        return None
    entry = outcome.round_trip.entry_price
    if entry <= 0:
        return None
    min_low = min(bar.low for bar in outcome.price_path)
    return (entry - min_low) / entry


def mfe(outcome: DecisionOutcome) -> float | None:
    """Maximum Favorable Excursion: best intra-holding gain from entry."""
    if not outcome.price_path or outcome.round_trip is None:
        return None
    entry = outcome.round_trip.entry_price
    if entry <= 0:
        return None
    max_high = max(bar.high for bar in outcome.price_path)
    return (max_high - entry) / entry


def stop_quality(outcome: DecisionOutcome, post_trigger_days: int = 5) -> str:
    """Evaluate whether the stop was noise or appropriate."""
    d = outcome.decision
    if d.stop is None:
        return "n/a"
    if not outcome.price_path:
        return "n/a"

    stop_triggered = any(bar.low <= d.stop for bar in outcome.price_path)
    if not stop_triggered:
        near_stop = any(bar.low <= d.stop * 1.02 for bar in outcome.price_path)
        return "held" if near_stop else "n/a"

    trigger_idx = next(
        i for i, bar in enumerate(outcome.price_path) if bar.low <= d.stop
    )
    post = outcome.price_path[trigger_idx + 1: trigger_idx + 1 + post_trigger_days]
    if not post:
        return "appropriate"
    recovered = any(bar.close > d.stop * 1.03 for bar in post)
    return "noise_hit" if recovered else "appropriate"


def target_quality(outcome: DecisionOutcome) -> dict:
    """Whether target was reached and how long it took."""
    d = outcome.decision
    if d.target is None or not outcome.price_path:
        return {"reached": False, "days_to_reach": None}
    for i, bar in enumerate(outcome.price_path):
        if bar.high >= d.target:
            return {"reached": True, "days_to_reach": i}
    return {"reached": False, "days_to_reach": None}


def confidence_calibration(outcomes: list[DecisionOutcome], horizon: int = 5) -> dict:
    """Calibration by confidence bucket. Excludes unscored (0.5 or None)."""
    buckets = {
        "0.0-0.49": {"count": 0, "hits": 0},
        "0.51-0.7": {"count": 0, "hits": 0},
        "0.7-0.9": {"count": 0, "hits": 0},
        "0.9-1.0": {"count": 0, "hits": 0},
    }

    def _bucket(c: float) -> str | None:
        if abs(c - 0.5) < 0.01:
            return None
        if c < 0.5:
            return "0.0-0.49"
        if c <= 0.7:
            return "0.51-0.7"
        if c <= 0.9:
            return "0.7-0.9"
        return "0.9-1.0"

    for o in outcomes:
        if o.decision.action != "BUY" or len(o.price_path) <= 1:
            continue
        c = o.decision.confidence
        if c is None:
            continue
        b = _bucket(c)
        if b is None:
            continue
        buckets[b]["count"] += 1
        entry = o.price_path[0].close
        end_idx = min(horizon, len(o.price_path) - 1)
        if o.price_path[end_idx].close > entry:
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
    """Realized risk:reward vs planned. None if no stop/target or no round-trip."""
    d = outcome.decision
    rt = outcome.round_trip
    if d.stop is None or d.target is None or rt is None:
        return None
    entry = d.limit if d.limit is not None else rt.entry_price
    planned_risk = abs(entry - d.stop)
    if planned_risk <= 0:
        return None
    actual_pnl = rt.exit_price - rt.entry_price
    return actual_pnl / planned_risk


def benchmark_excess(
    outcome: DecisionOutcome,
    spy_path: list[dict] | None,
    qqq_path: list[dict] | None,
) -> dict:
    """Excess return vs SPY/QQQ over the same holding period."""
    result: dict[str, float | None] = {"vs_spy": None, "vs_qqq": None}
    if not outcome.price_path or len(outcome.price_path) < 2:
        return result
    stock_return = (outcome.price_path[-1].close / outcome.price_path[0].close) - 1

    for bench_name, bench_path in [("vs_spy", spy_path), ("vs_qqq", qqq_path)]:
        if bench_path and len(bench_path) >= 2:
            start_close = bench_path[0].close if hasattr(bench_path[0], "close") else bench_path[0]["close"]
            end_close = bench_path[-1].close if hasattr(bench_path[-1], "close") else bench_path[-1]["close"]
            if start_close <= 0:
                continue
            bench_return = (end_close / start_close) - 1
            result[bench_name] = stock_return - bench_return
    return result


def exit_timing(outcome: DecisionOutcome, horizon: int = 5) -> float | None:
    """SELL-only: opportunity cost — price change after exit.
    Positive = left money on the table; negative = good timing."""
    if outcome.decision.action != "SELL":
        return None
    if not outcome.price_path or len(outcome.price_path) < 2:
        return None
    exit_price = outcome.price_path[0].close
    end_idx = min(horizon, len(outcome.price_path) - 1)
    post_price = outcome.price_path[end_idx].close
    if exit_price <= 0:
        return None
    return (post_price - exit_price) / exit_price
