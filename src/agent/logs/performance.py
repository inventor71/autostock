"""Portfolio-vs-benchmark performance — the "am I beating the S&P 500?" scorecard.

Read-time derivation over the existing equity log: ``equity.jsonl`` already records
one EOD line per day with the account ``equity`` and the day's ``benchmark.SPY``
mark (see :mod:`src.agent.logs.equity`). This module joins those two series into a
single headline — agent cumulative return vs a SPY buy-and-hold of the same money,
plus the excess (alpha) and today's delta — without persisting anything new or
touching the EOD pipeline. Missing/short data yields ``None`` (fail-honest); the
snapshot publisher and dashboards fold it in additively.
"""

from __future__ import annotations

from pathlib import Path


def _pos_float(x) -> float | None:
    """Coerce to a strictly-positive float, else None (filters junk/zero marks)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def compute_performance(records: list[dict], *, benchmark_key: str = "SPY") -> dict | None:
    """Agent vs SPY buy-and-hold headline from equity-log records (pure, no I/O).

    ``records`` are ``equity.jsonl`` lines (oldest first). A record is *usable* only
    if it has a positive ``equity`` AND a positive ``benchmark[benchmark_key]`` — so
    early lines written before the benchmark was captured are skipped and the
    baseline is the first day the index mark exists.

    Cumulative return is a ratio to the baseline price, so it is independent of the
    starting capital amount: it answers "had I put the same money in SPY instead."

    Returns a JSON-serializable dict, or ``None`` if no usable record exists.
    """
    usable: list[tuple[str, float, float]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        eq = _pos_float(rec.get("equity"))
        if eq is None:
            continue
        bench = rec.get("benchmark") or {}
        spy = _pos_float(bench.get(benchmark_key)) if isinstance(bench, dict) else None
        if spy is None:
            continue
        usable.append((str(rec.get("date") or ""), eq, spy))

    if not usable:
        return None

    base_date, base_eq, base_spy = usable[0]
    _, last_eq, last_spy = usable[-1]

    agent_return_pct = round((last_eq / base_eq - 1) * 100, 2)
    spy_return_pct = round((last_spy / base_spy - 1) * 100, 2)
    alpha_pct = round(agent_return_pct - spy_return_pct, 2)

    agent_day_pct = spy_day_pct = day_alpha_pct = None
    if len(usable) >= 2:
        _, prev_eq, prev_spy = usable[-2]
        agent_day_pct = round((last_eq / prev_eq - 1) * 100, 2)
        spy_day_pct = round((last_spy / prev_spy - 1) * 100, 2)
        day_alpha_pct = round(agent_day_pct - spy_day_pct, 2)

    return {
        "since_date": base_date,
        "days": len(usable),
        "agent_return_pct": agent_return_pct,
        "spy_return_pct": spy_return_pct,
        "alpha_pct": alpha_pct,
        "agent_day_pct": agent_day_pct,
        "spy_day_pct": spy_day_pct,
        "day_alpha_pct": day_alpha_pct,
    }


def load_performance(path: str | Path | None = None) -> dict | None:
    """Read the equity log and compute the performance headline; None on any failure."""
    from src.agent.logs.equity import default_path, read_equity

    try:
        return compute_performance(read_equity(path or default_path()))
    except Exception:
        return None


def _fmt(pct: float | None) -> str:
    return f"{pct:+.2f}%" if pct is not None else "—"


def main() -> None:
    """Print the agent-vs-SPY headline from the live equity log:
    ``python -m src.agent.logs.performance``"""
    perf = load_performance()
    if not perf:
        print("성과 데이터 부족 — equity.jsonl에 SPY 벤치마크가 있는 기록이 아직 없습니다.")
        return
    print(
        f"vs S&P500 (since {perf['since_date']}, {perf['days']} days):\n"
        f"  Agent  {_fmt(perf['agent_return_pct'])}\n"
        f"  SPY    {_fmt(perf['spy_return_pct'])}\n"
        f"  Alpha  {_fmt(perf['alpha_pct'])}"
        f"   (today: agent {_fmt(perf['agent_day_pct'])} vs SPY {_fmt(perf['spy_day_pct'])}"
        f" = {_fmt(perf['day_alpha_pct'])})"
    )


if __name__ == "__main__":
    main()
