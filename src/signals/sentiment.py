"""Retail-sentiment history + baseline math (F77) — pure core, thin I/O.

History lives under ``workspace/sentiment/<ET-date>.jsonl`` (one line per
symbol per sweep, append-only — F72 screening precedent). The pure functions
turn that history into per-symbol baselines and z-scored outliers; StockTwits
rests ~75% bullish, so only deviation from a symbol's OWN baseline is signal.

All I/O is fail-honest: a read failure degrades to "no sentiment section",
never an exception into the research turn (NFR-1). Agent-package imports are
lazy to keep ``signals`` import-time independent of ``agent``.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.signals.records import SentimentOutlier, SentimentRecord
from src.signals.settings import SentimentConfig

SENTIMENT_DIR = "sentiment"


def resolve_root(root: str | Path | None = None) -> Path:
    """Workspace root shared with the daemon (same contract as screening_log)."""
    if root is not None:
        return Path(root)
    env = os.environ.get("AGENT_JOURNAL_ROOT")
    if env:
        return Path(env)
    from src.agent.journal import DEFAULT_ROOT  # lazy: avoid agent<->signals import cycle
    return Path(DEFAULT_ROOT)


def day_path(root: str | Path, et_date: str) -> Path:
    return Path(root) / SENTIMENT_DIR / f"{et_date}.jsonl"


# --------------------------------------------------------------------------- #
# Pure core (PBT targets)
# --------------------------------------------------------------------------- #
def bull_ratio(bullish_n: int, bearish_n: int) -> float | None:
    """bullish/(bullish+bearish) in [0,1]; None when nothing is tagged."""
    tagged = bullish_n + bearish_n
    if tagged <= 0:
        return None
    return bullish_n / tagged


@dataclass(frozen=True)
class Baseline:
    """Per-symbol baseline over the history window."""

    n_points: int
    ratio_mean: float | None
    ratio_std: float | None
    tagged_mean: float | None
    tagged_std: float | None


def baseline(history: list[SentimentRecord]) -> Baseline:
    """Mean/std of bull-ratio and tagged-volume over past sweep points.

    Points with nothing tagged contribute to volume stats (tagged=0) but not to
    ratio stats (ratio undefined).
    """
    ratios = [r for r in (bull_ratio(h.bullish_n, h.bearish_n) for h in history)
              if r is not None]
    tagged = [float(h.bullish_n + h.bearish_n) for h in history]

    def _mean_std(xs: list[float]) -> tuple[float | None, float | None]:
        if not xs:
            return None, None
        mean = sum(xs) / len(xs)
        if len(xs) < 2:
            return mean, None
        var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
        return mean, math.sqrt(var)

    ratio_mean, ratio_std = _mean_std(ratios)
    tagged_mean, tagged_std = _mean_std(tagged)
    return Baseline(
        n_points=len(history),
        ratio_mean=ratio_mean, ratio_std=ratio_std,
        tagged_mean=tagged_mean, tagged_std=tagged_std,
    )


def zscore(value: float | None, mean: float | None, std: float | None) -> float | None:
    """(value-mean)/std; None whenever undefined (no sample, std 0/None)."""
    if value is None or mean is None or std is None or std <= 0.0:
        return None
    return (value - mean) / std


def select_outliers(
    currents: list[SentimentRecord],
    baselines: dict[str, Baseline],
    cfg: SentimentConfig,
) -> list[SentimentOutlier]:
    """Symbols whose current sweep deviates from their own baseline (FR-3).

    Cold-start symbols (few baseline points) and thin snapshots (few tagged
    messages) are cut before thresholding; survivors are ranked by max |z|
    and capped at ``top_k``.
    """
    out: list[tuple[float, SentimentOutlier]] = []
    for cur in currents:
        base = baselines.get(cur.symbol)
        if base is None or base.n_points < cfg.min_baseline_points:
            continue
        tagged_n = cur.bullish_n + cur.bearish_n
        if tagged_n < cfg.min_tagged:
            continue
        ratio = bull_ratio(cur.bullish_n, cur.bearish_n)
        if ratio is None or base.ratio_mean is None:
            continue
        ratio_z = zscore(ratio, base.ratio_mean, base.ratio_std)
        volume_z = zscore(float(tagged_n), base.tagged_mean, base.tagged_std)
        score = max(abs(ratio_z) if ratio_z is not None else 0.0,
                    abs(volume_z) if volume_z is not None else 0.0)
        if score < cfg.z_threshold:
            continue
        out.append((score, SentimentOutlier(
            symbol=cur.symbol,
            bull_ratio=ratio,
            baseline_ratio=base.ratio_mean,
            ratio_z=ratio_z,
            volume_z=volume_z,
            tagged_n=tagged_n,
            direction="bullish" if ratio >= base.ratio_mean else "bearish",
        )))
    out.sort(key=lambda t: t[0], reverse=True)
    return [o for _, o in out[: cfg.top_k]]


# --------------------------------------------------------------------------- #
# Thin I/O (fail-honest)
# --------------------------------------------------------------------------- #
def append_sweep(
    records: list[SentimentRecord],
    root: str | Path | None = None,
    ts: datetime | None = None,
) -> Path | None:
    """Append one sweep's records to the ET-date file. None on any failure —
    persistence must never sink the sweep (NFR-1)."""
    try:
        from src.agent.logs.turn import compute_et_date  # lazy (see module docstring)

        now = ts or datetime.now().astimezone()
        path = day_path(resolve_root(root), compute_et_date(now))
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(
            json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for r in records
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines)
        return path
    except Exception as exc:
        logger.warning("sentiment sweep not persisted ({}); sweep unaffected", exc)
        return None


def load_recent(
    root: str | Path | None = None,
    *,
    days: int,
    now: datetime | None = None,
) -> dict[str, list[SentimentRecord]]:
    """Per-symbol history from the last ``days`` ET-date files (lenient parse:
    torn/corrupt lines are skipped). Empty dict when nothing exists."""
    from src.agent.logs.turn import compute_et_date  # lazy

    base = resolve_root(root)
    now = now or datetime.now().astimezone()
    history: dict[str, list[SentimentRecord]] = {}
    for back in range(days, -1, -1):
        path = day_path(base, compute_et_date(now - timedelta(days=back)))
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = SentimentRecord.model_validate(json.loads(line))
            except Exception:
                continue
            history.setdefault(rec.symbol, []).append(rec)
    return history


def current_outliers(
    cfg: SentimentConfig,
    *,
    symbols: list[str] | None = None,
    root: str | Path | None = None,
    now: datetime | None = None,
) -> list[SentimentOutlier]:
    """One-call read path: history → fresh currents → z-scored outliers.

    ``symbols`` restricts the result (intraday: held/watchlist only); None means
    the whole recorded universe (research brief). A "current" point older than
    ``max_age_minutes`` is dropped so a stopped sweep can't surface stale
    outliers. Raises on read/compute failure — the caller decides whether that
    is degraded (collector) or silent (intraday)."""
    history = load_recent(root, days=cfg.baseline_days, now=now)
    if not history:
        return []
    currents, baselines = latest_and_baselines(history)
    cutoff = (now or datetime.now().astimezone()) - timedelta(minutes=cfg.max_age_minutes)
    currents = [c for c in currents if c.ts.tzinfo is not None and c.ts >= cutoff]
    if symbols is not None:
        wanted = {s.strip().upper() for s in symbols}
        currents = [c for c in currents if c.symbol in wanted]
    return select_outliers(currents, baselines, cfg)


def outlier_lines_for(
    symbols: list[str],
    cfg: SentimentConfig,
    root: str | Path | None = None,
) -> list[str]:
    """Compact intraday-brief lines for outliers among ``symbols``.

    Fail-honest: any failure (or cold start) is an empty list — the intraday
    brief must assemble regardless."""
    try:
        outliers = current_outliers(cfg, symbols=symbols, root=root)
    except Exception as exc:
        logger.debug("sentiment intraday lines skipped ({})", exc)
        return []
    lines = []
    for o in outliers:
        rz = f"z={o.ratio_z:+.1f}" if o.ratio_z is not None else "z=?"
        lines.append(
            f"  sentiment {o.symbol}: bull {o.bull_ratio:.0%} "
            f"(usually {o.baseline_ratio:.0%}, {rz}, n={o.tagged_n}) — {o.direction} shift"
        )
    return lines


def latest_and_baselines(
    history: dict[str, list[SentimentRecord]],
) -> tuple[list[SentimentRecord], dict[str, Baseline]]:
    """Split per-symbol history into (latest point, baseline over the rest)."""
    currents: list[SentimentRecord] = []
    baselines: dict[str, Baseline] = {}
    for symbol, recs in history.items():
        if not recs:
            continue
        recs = sorted(recs, key=lambda r: r.ts)
        currents.append(recs[-1])
        baselines[symbol] = baseline(recs[:-1])
    return currents, baselines
