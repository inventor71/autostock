"""F65 hybrid-recall tests: fingerprint, pure prefilter ranking, LLM-rerank
fallback, lesson_id rendering, and retirement — all deterministic."""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from src.agent.learning.efficacy import LessonEfficacy
from src.agent.journal import LessonRecord
from src.agent.learning.recall import (
    RecallWeights,
    SituationFingerprint,
    build_fingerprint,
    build_lesson_context,
    mark_retirements,
    prefilter_and_rank,
    recall_lessons,
)

TODAY = date(2026, 6, 5)


def _lesson(lid, *, days_ago=0, regime="", sector=None, category="other", takeaway="t"):
    return LessonRecord(
        lesson_id=lid,
        date=(TODAY - timedelta(days=days_ago)).isoformat(),
        category=category,
        regime=regime,
        sector=sector,
        takeaway=takeaway,
    )


def _eff(lid, applied_n, avg_excess):
    wr = None if applied_n == 0 else (1.0 if (avg_excess or 0) > 0 else 0.0)
    return LessonEfficacy(lesson_id=lid, applied_n=applied_n, win_rate=wr, avg_excess=avg_excess)


# --------------------------------------------------------------------------- #
# fingerprint
# --------------------------------------------------------------------------- #
def test_build_fingerprint_full_text_and_dedup():
    # Non-comment lines are joined (not just line 1) so a regime keyword
    # mentioned anywhere matches; comment/heading lines are dropped.
    fp = build_fingerprint(
        regime_text="# Market Regime\nBull, low vol\nmore",
        held_sectors=["Tech", "tech", "Energy"],
    )
    assert fp.regime == "bull, low vol more"
    assert fp.sectors == ("energy", "tech")


def test_build_fingerprint_empty():
    fp = build_fingerprint()
    assert fp == SituationFingerprint(regime="", sectors=(), action_categories=())


# --------------------------------------------------------------------------- #
# prefilter ranking
# --------------------------------------------------------------------------- #
def test_verified_positive_outranks_unverified_lucky():
    lessons = [_lesson("L1"), _lesson("L2")]
    fp = SituationFingerprint()
    eff = {
        "L1": _eff("L1", applied_n=50, avg_excess=0.04),  # verified, strong
        "L2": _eff("L2", applied_n=1, avg_excess=0.50),   # lucky single hit, unverified
    }
    ranked = prefilter_and_rank(lessons, fp, eff, RecallWeights(), k_prime=10, today=TODAY)
    assert ranked[0].lesson.lesson_id == "L1"
    assert ranked[0].verified is True
    assert ranked[1].verified is False  # L2's huge excess is capped to 0


def test_relevance_boosts_regime_match():
    lessons = [_lesson("L1"), _lesson("L2", regime="high-vol")]
    fp = SituationFingerprint(regime="high-vol gap risk")
    ranked = prefilter_and_rank(lessons, fp, {}, RecallWeights(), k_prime=10, today=TODAY)
    assert ranked[0].lesson.lesson_id == "L2"  # regime match wins with no efficacy
    assert ranked[0].relevance == 1


def test_relevance_matches_regime_keyword_on_later_line():
    # The keyword sits on line 2+ of regime.md (line 1 is a heading) and is a
    # hyphenated tag — the old first-line-only word-boundary regex missed both.
    fp = build_fingerprint(regime_text="# Regime\nChoppy tape, risk-off into the close")
    lessons = [_lesson("L1"), _lesson("L2", regime="risk-off")]
    ranked = prefilter_and_rank(lessons, fp, {}, RecallWeights(), k_prime=10, today=TODAY)
    assert ranked[0].lesson.lesson_id == "L2"
    assert ranked[0].relevance == 1


def test_ranking_is_deterministic_tiebreak():
    lessons = [_lesson("L3"), _lesson("L1"), _lesson("L2")]  # identical scores
    fp = SituationFingerprint()
    a = prefilter_and_rank(lessons, fp, {}, RecallWeights(), k_prime=10, today=TODAY)
    assert [s.lesson.lesson_id for s in a] == ["L1", "L2", "L3"]  # tie -> lesson_id


def test_exclude_drops_retired():
    lessons = [_lesson("L1"), _lesson("L2")]
    ranked = prefilter_and_rank(
        lessons, SituationFingerprint(), {}, RecallWeights(), k_prime=10,
        today=TODAY, exclude={"L1"},
    )
    assert [s.lesson.lesson_id for s in ranked] == ["L2"]


# --------------------------------------------------------------------------- #
# recall_lessons + rerank fallback
# --------------------------------------------------------------------------- #
def test_recall_pure_path_returns_top_k():
    lessons = [_lesson(f"L{i}", days_ago=i) for i in range(5)]
    out = recall_lessons(lessons, SituationFingerprint(), {}, k=2, today=TODAY)
    assert len(out) == 2
    assert out[0].lesson_id == "L0"  # most recent ranks first (no efficacy/relevance)


def test_recall_rerank_reorders_when_valid():
    lessons = [_lesson("L1"), _lesson("L2")]

    def rerank(candidates, fp, k):
        return ["L2", "L1"]  # flip order

    out = recall_lessons(lessons, SituationFingerprint(), {}, k=2, rerank_fn=rerank, today=TODAY)
    assert [r.lesson_id for r in out] == ["L2", "L1"]


def test_recall_falls_back_when_rerank_raises():
    lessons = [_lesson("L1", days_ago=0), _lesson("L2", days_ago=5)]

    def boom(candidates, fp, k):
        raise RuntimeError("LLM turn died")

    out = recall_lessons(lessons, SituationFingerprint(), {}, k=2, rerank_fn=boom, today=TODAY)
    assert [r.lesson_id for r in out] == ["L1", "L2"]  # pure order preserved


def test_recall_falls_back_when_rerank_returns_junk():
    lessons = [_lesson("L1"), _lesson("L2")]

    def junk(candidates, fp, k):
        return ["NOPE", "ALSO_NOPE"]

    out = recall_lessons(lessons, SituationFingerprint(), {}, k=2, rerank_fn=junk, today=TODAY)
    assert {r.lesson_id for r in out} == {"L1", "L2"}  # fell back, not empty


# --------------------------------------------------------------------------- #
# rendering (lesson_id must be present — the critic fix)
# --------------------------------------------------------------------------- #
def test_build_lesson_context_includes_lesson_id():
    ctx = build_lesson_context([_lesson("L007", takeaway="widen stops in high vol")])
    assert "L007" in ctx
    assert "lessons_cited" in ctx  # tells the agent to cite


def test_build_lesson_context_empty():
    assert build_lesson_context([]) == ""


# --------------------------------------------------------------------------- #
# retirement
# --------------------------------------------------------------------------- #
def test_mark_retirements_flags_verified_negative_and_idle():
    lessons = [
        _lesson("L1"),                       # verified positive -> keep
        _lesson("L2"),                       # verified negative -> retire
        _lesson("L3", days_ago=400),         # old + unused -> retire
        _lesson("L4", days_ago=400),         # old but used -> keep
    ]
    eff = {
        "L1": _eff("L1", 30, 0.03),
        "L2": _eff("L2", 30, -0.02),
        "L4": _eff("L4", 5, 0.01),
    }
    retired = set(mark_retirements(lessons, eff, today=TODAY, idle_days=180))
    assert retired == {"L2", "L3"}


# --------------------------------------------------------------------------- #
# PBT invariants
# --------------------------------------------------------------------------- #
@given(st.integers(min_value=0, max_value=30), st.integers(min_value=1, max_value=15))
def test_recall_never_exceeds_k_and_never_raises(n_lessons, k):
    lessons = [_lesson(f"L{i:03d}", days_ago=i) for i in range(n_lessons)]
    out = recall_lessons(lessons, SituationFingerprint(), {}, k=k, today=TODAY)
    assert len(out) <= k
    assert len(out) <= n_lessons
