"""F65: situational lesson recall — replaces recency-only injection.

Old behavior (``prompts._build_lesson_context``): inject the last N lessons by
date. A lesson about high-VIX gap-downs crowds out a relevant trend-day lesson
and there is no efficacy ranking.

This module selects the lessons most relevant to *today's* situation and ranks
them by demonstrated efficacy (F62). The pipeline is hybrid:
  1. build a situation fingerprint (pure)
  2. tag-prefilter + efficacy/relevance/recency ranking (pure, unit-tested)
  3. OPTIONAL LLM rerank of the shortlist (injected ``rerank_fn``) with a
     graceful fallback to the pure order — recall never fails or returns empty
     because of a bad rerank turn.

Only step 3 is nondeterministic, and it is injected so the rest stays testable.
``efficacy`` is supplied by the caller (orchestrator caches it); an empty dict
degrades ranking gracefully to relevance + recency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from loguru import logger

from src.agent.efficacy import LessonEfficacy
from src.agent.journal import LessonRecord


@dataclass(frozen=True)
class RecallWeights:
    efficacy: float = 1.0
    recency: float = 0.5
    relevance: float = 0.75
    # A lesson is "verified" (its efficacy is trusted) only above this sample
    # size; below it, the efficacy term is capped to 0 so a lucky single hit
    # can't rocket an unproven lesson to the top.
    min_verified: int = 20


@dataclass(frozen=True)
class SituationFingerprint:
    regime: str = ""
    sectors: tuple[str, ...] = ()
    action_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredLesson:
    lesson: LessonRecord
    score: float
    verified: bool
    relevance: int = field(default=0)


def build_fingerprint(
    regime_text: str | None = None,
    held_sectors: list[str] | None = None,
    pending_categories: list[str] | None = None,
) -> SituationFingerprint:
    """Assemble today's situation key from journal/market context (pure)."""
    # Full searchable haystack: every non-comment line of regime.md joined and
    # lowercased (not just line 1) so a regime tag mentioned anywhere matches.
    regime = " ".join(
        ln.strip() for ln in (regime_text or "").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ).lower()
    return SituationFingerprint(
        regime=regime,
        sectors=tuple(sorted({s.lower() for s in (held_sectors or []) if s})),
        action_categories=tuple(sorted({c for c in (pending_categories or []) if c})),
    )


def _recency(lesson_date: str, today: date) -> float:
    """1/(1+age_days), clamped to [0,1]. Unparseable date -> 0 (neutral)."""
    try:
        d = date.fromisoformat(lesson_date)
    except (ValueError, TypeError):
        return 0.0
    age = max((today - d).days, 0)
    return 1.0 / (1.0 + age)


def _relevance(lesson: LessonRecord, fp: SituationFingerprint) -> int:
    """Count of fingerprint tag matches. Untagged lessons score 0 (neutral) —
    they are never filtered out, only out-ranked when a tagged peer matches."""
    score = 0
    # Substring match (like sector below) — robust to hyphenated/multi-word tags
    # ('risk-off') that word-boundary regex mishandles.
    if lesson.regime and fp.regime and lesson.regime.lower() in fp.regime:
        score += 1
    if lesson.sector and lesson.sector.lower() in fp.sectors:
        score += 1
    if lesson.category and lesson.category in fp.action_categories:
        score += 1
    return score


def prefilter_and_rank(
    lessons: list[LessonRecord],
    fp: SituationFingerprint,
    efficacy: dict[str, LessonEfficacy],
    weights: RecallWeights,
    k_prime: int,
    *,
    today: date | None = None,
    exclude: set[str] | None = None,
) -> list[ScoredLesson]:
    """Pure ranking. Returns the top ``k_prime`` ScoredLessons.

    score = w_e * eff_term + w_r * recency + w_rel * relevance
      eff_term = avg_excess when the lesson is VERIFIED (applied_n >= min), else 0
      recency  = 1/(1+age_days)
      relevance= tag-match count vs the fingerprint
    Deterministic: ties broken by lesson_id (stable).
    """
    today = today or date.today()
    exclude = exclude or set()
    scored: list[ScoredLesson] = []
    for lesson in lessons:
        if lesson.lesson_id in exclude:
            continue
        eff = efficacy.get(lesson.lesson_id)
        verified = bool(eff and eff.applied_n >= weights.min_verified and eff.avg_excess is not None)
        eff_term = eff.avg_excess if (verified and eff is not None and eff.avg_excess is not None) else 0.0
        rel = _relevance(lesson, fp)
        score = (
            weights.efficacy * eff_term
            + weights.recency * _recency(lesson.date, today)
            + weights.relevance * rel
        )
        scored.append(ScoredLesson(lesson=lesson, score=score, verified=verified, relevance=rel))
    scored.sort(key=lambda s: (-s.score, s.lesson.lesson_id))
    return scored[:k_prime]


def recall_lessons(
    lessons: list[LessonRecord],
    fp: SituationFingerprint,
    efficacy: dict[str, LessonEfficacy],
    *,
    k: int = 10,
    k_prime: int = 20,
    weights: RecallWeights | None = None,
    rerank_fn=None,
    today: date | None = None,
    exclude: set[str] | None = None,
) -> list[LessonRecord]:
    """Full hybrid recall. Pure prefilter, then OPTIONAL LLM rerank of the
    shortlist with graceful fallback. Always returns <= k lessons, never raises.

    ``rerank_fn(candidates, fp, k) -> list[str]`` returns selected lesson_ids in
    preference order. Any failure (exception, empty, unknown ids) falls back to
    the pure prefilter order.
    """
    weights = weights or RecallWeights()
    shortlist = prefilter_and_rank(
        lessons, fp, efficacy, weights, k_prime, today=today, exclude=exclude
    )
    ordered = [s.lesson for s in shortlist]
    if rerank_fn is None:
        return ordered[:k]
    try:
        by_id = {s.lesson.lesson_id: s.lesson for s in shortlist}
        picked = rerank_fn(shortlist, fp, k)
        selected = [by_id[i] for i in picked if i in by_id]
        if not selected:
            raise ValueError("rerank returned no valid ids")
        return selected[:k]
    except Exception as exc:  # rerank must never sink recall
        logger.warning(f"recall rerank failed, using pure order: {exc}")
        return ordered[:k]


def build_lesson_context(lessons: list[LessonRecord], max_n: int = 10) -> str:
    """Render selected lessons for prompt injection — WITH lesson_id so the agent
    can cite them back in ``lessons_cited`` (F62 attribution loop)."""
    if not lessons:
        return ""
    lines = ["\n## Lessons relevant to today (apply these; cite the id in lessons_cited):"]
    for r in lessons[:max_n]:
        lines.append(f"- [{r.lesson_id}] [{r.category}] {r.takeaway}")
    return "\n".join(lines)


def mark_retirements(
    lessons: list[LessonRecord],
    efficacy: dict[str, LessonEfficacy],
    *,
    min_sample: int = 20,
    today: date | None = None,
    idle_days: int = 180,
) -> list[str]:
    """Pure: lesson_ids that have earned retirement — a verified-but-negative
    efficacy, or long idleness. Persistence (rewriting lessons.jsonl with a
    retired flag, EOD-only) is a documented follow-up; callers can pass the
    returned ids as ``exclude`` to ``recall_lessons`` in the meantime.
    """
    today = today or date.today()
    out: list[str] = []
    for lesson in lessons:
        eff = efficacy.get(lesson.lesson_id)
        if eff and eff.applied_n >= min_sample and eff.avg_excess is not None and eff.avg_excess < 0:
            out.append(lesson.lesson_id)
            continue
        try:
            age = (today - date.fromisoformat(lesson.date)).days
        except (ValueError, TypeError):
            age = 0
        if age >= idle_days and (eff is None or eff.applied_n == 0):
            out.append(lesson.lesson_id)
    return out
