"""F62: lesson / prompt-version efficacy — the attribution layer the agent
self-learning epic (F65 recall, F64 self-rewrite) consumes.

This is a thin, PURE aggregation over the F24 quality pipeline: it groups the
``DecisionOutcome`` records produced by ``src.agent.quality.collector`` by each
decision's ``lessons_cited`` / ``prompt_version`` and reduces the (now attached)
direction-aware ``excess`` into per-lesson / per-version stats. No LLM calls, no
I/O, no network — the network/price work already happened in the collector, so
every function here is deterministic and unit-testable on synthetic data.

Two distinct counts, deliberately kept separate:
  - ``applied_counts``        : how many times each lesson was *cited* across all
                                decisions (the derived ``times_applied`` — usage).
  - ``LessonEfficacy.applied_n``: how many of those citations have a *measurable*
                                outcome (excess is not None) — the sample size
                                backing ``win_rate`` / ``avg_excess``.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from src.agent.journal import Decision
from src.agent.quality.models import DecisionOutcome


class LessonEfficacy(BaseModel):
    lesson_id: str
    applied_n: int  # outcomes (with excess) attributed to this lesson
    win_rate: float | None  # fraction with excess > 0; None when applied_n == 0
    avg_excess: float | None  # mean excess; None when applied_n == 0


class VersionEfficacy(BaseModel):
    prompt_version: str
    applied_n: int
    win_rate: float | None
    avg_excess: float | None


def applied_counts(decisions: list[Decision]) -> dict[str, int]:
    """Derived ``times_applied``: total citations per lesson across decisions.

    The stored ``LessonRecord.times_applied`` is never incremented in place (it
    would race the cross-process agent appender on append-only lessons.jsonl);
    this pure Σ over ``lessons_cited`` is the authoritative usage count.
    """
    counts: dict[str, int] = defaultdict(int)
    for d in decisions:
        for lid in d.lessons_cited:
            counts[lid] += 1
    return dict(counts)


def _reduce(excesses: list[float]) -> tuple[int, float | None, float | None]:
    if not excesses:
        return 0, None, None
    n = len(excesses)
    win_rate = sum(1 for e in excesses if e > 0) / n
    avg_excess = sum(excesses) / n
    return n, win_rate, avg_excess


def lesson_efficacy(outcomes: list[DecisionOutcome]) -> dict[str, LessonEfficacy]:
    """Per-lesson efficacy, keyed by ``lesson_id``.

    Buckets the excess of every outcome whose decision cites the lesson. Outcomes
    without a measurable excess (exits/HOLD/missing benchmark) are skipped — a
    lesson cited only by such decisions yields ``applied_n == 0`` and None stats.
    """
    buckets: dict[str, list[float]] = defaultdict(list)
    seen: set[str] = set()
    for o in outcomes:
        for lid in o.decision.lessons_cited:
            seen.add(lid)
            if o.excess is not None:
                buckets[lid].append(o.excess)
    out: dict[str, LessonEfficacy] = {}
    for lid in seen:
        n, wr, ae = _reduce(buckets.get(lid, []))
        out[lid] = LessonEfficacy(lesson_id=lid, applied_n=n, win_rate=wr, avg_excess=ae)
    return out


def prompt_version_efficacy(
    outcomes: list[DecisionOutcome],
) -> dict[str, VersionEfficacy]:
    """Per-prompt-version efficacy, keyed by ``prompt_version`` (default 'seed')."""
    buckets: dict[str, list[float]] = defaultdict(list)
    seen: set[str] = set()
    for o in outcomes:
        v = o.decision.prompt_version
        seen.add(v)
        if o.excess is not None:
            buckets[v].append(o.excess)
    out: dict[str, VersionEfficacy] = {}
    for v in seen:
        n, wr, ae = _reduce(buckets.get(v, []))
        out[v] = VersionEfficacy(prompt_version=v, applied_n=n, win_rate=wr, avg_excess=ae)
    return out


# Minimum applied-count for an efficacy reading to be trusted (not small-sample
# noise). Single source so F65 recall trust and F64 evolution gating never drift.
MIN_EFFICACY_SAMPLE = 20
