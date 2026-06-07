"""Alpha-vs-baseline metrics — pure computation, separate from I/O (NFR-4 / BR-6).

``compute_metrics`` takes equity series in, returns a metrics object out, with no
file access — so the durable source series can be re-analysed any time the formula
changes. ``load``/``persist`` and the ``__main__`` CLI wrap it for offline recompute.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime

from src.benchmark.models import (
    LLM_KEY,
    BaselineMetric,
    BenchmarkMetrics,
    EquitySnapshot,
)

# Annualization factor for Sharpe (rf=0). EOD cadence ≈ 252 trading days/yr.
DEFAULT_PERIODS_PER_YEAR = 252


def _returns(equities: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(equities, equities[1:]):
        if prev > 0:
            out.append(cur / prev - 1.0)
    return out


def _stdev(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def _max_drawdown(equities: list[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            mdd = min(mdd, e / peak - 1.0)
    return mdd


def _metric(strategy: str, snaps: list[EquitySnapshot], periods_per_year: int) -> BaselineMetric:
    equities = [s.equity for s in snaps]
    cum = (equities[-1] / equities[0] - 1.0) if len(equities) >= 2 and equities[0] > 0 else 0.0
    rets = _returns(equities)
    vol = _stdev(rets)
    mean_r = (sum(rets) / len(rets)) if rets else 0.0
    sharpe = (mean_r / vol * math.sqrt(periods_per_year)) if vol > 0 else 0.0
    return BaselineMetric(
        strategy=strategy,
        cum_return=cum,
        volatility=vol,
        max_drawdown=_max_drawdown(equities),
        sharpe=sharpe,
        n_points=len(snaps),
    )


def _common_window(
    by_strategy: dict[str, list[EquitySnapshot]]
) -> tuple[datetime | None, datetime | None]:
    """Intersection [max(first), min(last)] across all non-empty series (BR-5)."""
    firsts, lasts = [], []
    for snaps in by_strategy.values():
        if snaps:
            ordered = sorted(snaps, key=lambda s: s.ts)
            firsts.append(ordered[0].ts)
            lasts.append(ordered[-1].ts)
    if not firsts:
        return None, None
    return max(firsts), min(lasts)


def compute_metrics(
    by_strategy: dict[str, list[EquitySnapshot]],
    llm_key: str = LLM_KEY,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> BenchmarkMetrics:
    """Per-strategy metrics + alpha, all over the common overlapping window.

    Pure: identical input → identical output, no I/O. Strategies are truncated to
    the shared [start, end] so returns are compared over the same period.
    """
    start, end = _common_window(by_strategy)

    def in_window(snaps: list[EquitySnapshot]) -> list[EquitySnapshot]:
        ordered = sorted(snaps, key=lambda s: s.ts)
        if start is None or end is None:
            return ordered
        return [s for s in ordered if start <= s.ts <= end]

    metrics: dict[str, BaselineMetric] = {}
    for strategy, snaps in by_strategy.items():
        windowed = in_window(snaps)
        if windowed:
            metrics[strategy] = _metric(strategy, windowed, periods_per_year)

    llm = metrics.get(llm_key)
    baselines = [m for name, m in metrics.items() if name != llm_key]
    alpha = (
        {m.strategy: llm.cum_return - m.cum_return for m in baselines}
        if llm is not None
        else {}
    )
    return BenchmarkMetrics(
        window_start=start,
        window_end=end,
        llm=llm,
        baselines=baselines,
        alpha=alpha,
    )


# ── I/O wrappers (kept apart from the pure core) ─────────────────────────────

def load_all(storage_dir: str, strategies: list[str]) -> dict[str, list[EquitySnapshot]]:
    from src.benchmark.store import EquityRecorder

    rec = EquityRecorder(storage_dir)
    return {s: rec.load(s) for s in strategies}


def persist(metrics: BenchmarkMetrics, storage_dir: str) -> None:
    from datetime import datetime
    from pathlib import Path

    from src.core.jsonl import append_record

    if metrics.ts is None:
        metrics.ts = datetime.utcnow()
    path = Path(storage_dir) / "metrics" / f"{metrics.ts:%Y%m%dT%H%M%S}.jsonl"
    append_record(path, metrics)


def _discover_strategies(storage_dir: str) -> list[str]:
    from pathlib import Path

    eq = Path(storage_dir) / "equity"
    if not eq.exists():
        return []
    return sorted(p.stem for p in eq.glob("*.jsonl"))


def main(argv: list[str] | None = None) -> int:
    """CLI: recompute metrics from stored equity series (D3 offline extraction).

    Usage: python -m src.benchmark.metrics [storage_dir]
    """
    argv = argv if argv is not None else sys.argv[1:]
    storage_dir = argv[0] if argv else "data/benchmark"
    strategies = _discover_strategies(storage_dir)
    if not strategies:
        print(f"no equity series under {storage_dir}/equity/")
        return 1
    metrics = compute_metrics(load_all(storage_dir, strategies))
    persist(metrics, storage_dir)
    if metrics.llm is None:
        print(f"strategies={strategies} — no '{LLM_KEY}' series, alpha unavailable")
    else:
        print(f"window {metrics.window_start} → {metrics.window_end}")
        print(f"  llm cum_return={metrics.llm.cum_return:+.4f} sharpe={metrics.llm.sharpe:.2f}")
        for m in metrics.baselines:
            print(
                f"  {m.strategy:14s} cum_return={m.cum_return:+.4f} "
                f"alpha={metrics.alpha.get(m.strategy, 0.0):+.4f} (n={m.n_points})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
