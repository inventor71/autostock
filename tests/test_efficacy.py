"""F62 unit-attribution tests: schema backward-compat, derived counts, efficacy
aggregation, statistical guards (with PBT), restamp round-trip, and the
collector's direction-aware excess attachment."""

from __future__ import annotations

import pandas as pd
from hypothesis import given
from hypothesis import strategies as st

from src.agent.learning.efficacy import (
    LessonEfficacy,
    applied_counts,
    lesson_efficacy,
    prompt_version_efficacy,
)
from src.agent.journal import Decision, Journal, LessonRecord
from src.agent.quality.collector import _attach_excess
from src.agent.quality.models import OHLC, DecisionOutcome


# --------------------------------------------------------------------------- #
# Schema backward-compat (legacy lines have none of the new fields)
# --------------------------------------------------------------------------- #
def test_legacy_decision_line_parses_with_defaults():
    legacy = '{"ts": "2026-01-02T10:00:00", "symbol": "AAPL", "action": "BUY"}'
    d = Decision.model_validate_json(legacy)
    assert d.lessons_cited == []
    assert d.prompt_version == "seed"


def test_legacy_lesson_line_parses_with_defaults():
    legacy = '{"lesson_id": "L001", "takeaway": "buy the dip"}'
    r = LessonRecord.model_validate_json(legacy)
    assert r.regime == ""
    assert r.sector is None
    assert r.times_applied == 0


def test_new_fields_round_trip():
    d = Decision(symbol="msft", action="BUY", lessons_cited=["L007"], prompt_version="g3")
    again = Decision.model_validate_json(d.model_dump_json())
    assert again.lessons_cited == ["L007"]
    assert again.prompt_version == "g3"
    assert again.symbol == "MSFT"


# --------------------------------------------------------------------------- #
# applied_counts (derived times_applied)
# --------------------------------------------------------------------------- #
def test_applied_counts_sums_citations():
    decisions = [
        Decision(symbol="A", action="BUY", lessons_cited=["L1", "L2"]),
        Decision(symbol="B", action="BUY", lessons_cited=["L1"]),
        Decision(symbol="C", action="HOLD", lessons_cited=[]),
    ]
    assert applied_counts(decisions) == {"L1": 2, "L2": 1}


@given(
    st.lists(
        st.lists(st.sampled_from(["L1", "L2", "L3"]), max_size=4),
        max_size=20,
    )
)
def test_applied_counts_total_invariant(citations_per_decision):
    decisions = [
        Decision(symbol="X", action="BUY", lessons_cited=cites)
        for cites in citations_per_decision
    ]
    counts = applied_counts(decisions)
    assert sum(counts.values()) == sum(len(c) for c in citations_per_decision)


# --------------------------------------------------------------------------- #
# efficacy aggregation
# --------------------------------------------------------------------------- #
def _outcome(action: str, cites: list[str], excess: float | None, version: str = "seed"):
    return DecisionOutcome(
        decision=Decision(symbol="X", action=action, lessons_cited=cites, prompt_version=version),
        excess=excess,
    )


def test_lesson_efficacy_matches_hand_calc():
    outcomes = [
        _outcome("BUY", ["L1"], 0.05),
        _outcome("BUY", ["L1"], -0.01),
        _outcome("SELL_SHORT", ["L1", "L2"], 0.03),
        _outcome("BUY", ["L2"], None),  # no measurable excess
    ]
    eff = lesson_efficacy(outcomes)
    # L1: excesses [0.05, -0.01, 0.03] -> n=3, win 2/3, avg 0.0233...
    assert eff["L1"].applied_n == 3
    assert eff["L1"].win_rate == 2 / 3
    assert abs(eff["L1"].avg_excess - (0.05 - 0.01 + 0.03) / 3) < 1e-9
    # L2: only [0.03] has excess (the None one is skipped) -> n=1
    assert eff["L2"].applied_n == 1
    assert eff["L2"].win_rate == 1.0


def test_lesson_with_only_unmeasured_outcomes_is_zero():
    eff = lesson_efficacy([_outcome("BUY", ["L9"], None)])
    assert eff["L9"] == LessonEfficacy(lesson_id="L9", applied_n=0, win_rate=None, avg_excess=None)


def test_prompt_version_efficacy_groups_by_version():
    outcomes = [
        _outcome("BUY", [], 0.02, version="seed"),
        _outcome("BUY", [], 0.04, version="g1"),
        _outcome("BUY", [], -0.02, version="g1"),
    ]
    eff = prompt_version_efficacy(outcomes)
    assert eff["seed"].applied_n == 1 and eff["seed"].avg_excess == 0.02
    assert eff["g1"].applied_n == 2 and eff["g1"].win_rate == 0.5


def test_efficacy_order_invariant():
    outcomes = [_outcome("BUY", ["L1"], 0.05), _outcome("BUY", ["L1"], -0.01)]
    assert lesson_efficacy(outcomes) == lesson_efficacy(list(reversed(outcomes)))


# --------------------------------------------------------------------------- #
# restamp round-trip
# --------------------------------------------------------------------------- #
def test_restamp_decisions_rewrites_prompt_version(tmp_path):
    j = Journal(tmp_path)
    # simulate the LLM having written two raw lines (no prompt_version)
    j.decisions_file.write_text(
        Decision(symbol="A", action="BUY").model_dump_json() + "\n"
        + Decision(symbol="B", action="SELL").model_dump_json() + "\n",
        encoding="utf-8",
    )
    decisions = j.read_decisions()
    for d in decisions:
        d.prompt_version = "g5"
    j.restamp_decisions(decisions)
    reread = j.read_decisions()
    assert [d.prompt_version for d in reread] == ["g5", "g5"]
    assert len(reread) == 2  # no duplication / loss


# --------------------------------------------------------------------------- #
# collector direction-aware excess
# --------------------------------------------------------------------------- #
def _flat_bench(dates, close):
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close},
        index=pd.to_datetime(dates),
    )


def test_attach_excess_is_direction_aware():
    dates = ["2026-01-02", "2026-01-03", "2026-01-04"]
    rising = [OHLC(date=d, open=100, high=110, low=100, close=c) for d, c in zip(dates, [100, 105, 110])]
    ohlc_cache = {"SPY": _flat_bench(dates, 400.0), "QQQ": _flat_bench(dates, 300.0)}

    buy = DecisionOutcome(decision=Decision(symbol="X", action="BUY"), price_path=list(rising))
    shrt = DecisionOutcome(decision=Decision(symbol="Y", action="SELL_SHORT"), price_path=list(rising))
    exit_ = DecisionOutcome(decision=Decision(symbol="Z", action="SELL"), price_path=list(rising))

    _attach_excess([buy, shrt, exit_], ohlc_cache)

    # stock +10% vs flat benchmarks -> base excess +0.10
    assert buy.excess is not None and buy.excess > 0.09
    assert shrt.excess is not None and shrt.excess < -0.09  # inverted for shorts
    assert exit_.excess is None  # exits carry no entry-excess


# --------------------------------------------------------------------------- #
# execution-timestamp parsing (regression: naive ts must parse, not silently None)
# --------------------------------------------------------------------------- #
def test_parse_exec_ts_handles_naive_and_aware():
    from datetime import datetime, timezone

    from src.agent.quality.collector import _parse_exec_ts

    # Naive ISO (the common logged form) — must parse as UTC, NOT return None.
    naive = _parse_exec_ts("2026-06-05T14:30:00")
    assert naive is not None
    assert naive == datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc).timestamp()

    # tz-aware ISO parses too.
    aware = _parse_exec_ts("2026-06-05T14:30:00+00:00")
    assert aware is not None and aware == naive

    # Genuinely unparseable -> None (fail-safe).
    assert _parse_exec_ts("not-a-timestamp") is None
