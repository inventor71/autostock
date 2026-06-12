"""F68 follow-up: orchestrator self-learning wiring — per-day outcome cache
shared between recall and EOD self-rewrite (#8), and the rollback-skips-rewrite
guard (#7). Deterministic; no network (collect_outcomes is monkeypatched)."""

from __future__ import annotations

from datetime import date

from src.agent.orchestrator import AgentTradingLoop
from src.agent.session import AgentSession


def _loop(tmp_path):
    session = AgentSession(workspace=tmp_path, runner=lambda *a, **k: None,
                           session_date=date(2026, 6, 1))
    return AgentTradingLoop(session=session, universe=["AAPL"])


def test_outcomes_collected_once_per_day_across_efficacy_and_rewrite(tmp_path, monkeypatch):
    # collect_outcomes is the expensive (price-provider) step; both the recall
    # path (_lesson_efficacy) and the EOD self-rewrite must share ONE call/day.
    calls = []

    def fake_collect(journal):
        calls.append(1)
        return []  # empty outcomes → empty efficacy (fail-safe path)

    monkeypatch.setattr("src.agent.quality.collector.collect_outcomes", fake_collect)
    loop = _loop(tmp_path)

    loop._lesson_efficacy()          # 1st access — collects
    loop._lesson_efficacy()          # cached — no collect
    loop._run_self_rewrite()         # reuses the same cached outcomes
    assert len(calls) == 1


def test_cached_outcomes_failsafe_returns_empty(tmp_path, monkeypatch):
    def boom(journal):
        raise RuntimeError("price provider down")

    monkeypatch.setattr("src.agent.quality.collector.collect_outcomes", boom)
    loop = _loop(tmp_path)
    # Must not raise — degrades to empty efficacy so recall falls back cleanly.
    assert loop._lesson_efficacy() == {}
    assert loop._cached_outcomes() == []


def test_rollback_skips_rewrite_in_same_eod(tmp_path, monkeypatch):
    # When a version is auto-rolled-back, no rewrite is proposed the same EOD
    # (don't grow a new generation off the abandoned child — #7).
    monkeypatch.setattr("src.agent.quality.collector.collect_outcomes",
                        lambda journal: [])
    monkeypatch.setattr("src.agent.learning.self_rewrite.maybe_rollback",
                        lambda hist, ver_excess: True)  # rollback fired
    proposed = []
    monkeypatch.setattr("src.agent.learning.self_rewrite.propose_rewrite",
                        lambda *a, **k: proposed.append(1))
    monkeypatch.setattr("src.agent.learning.self_rewrite.save_history", lambda *a, **k: None)

    loop = _loop(tmp_path)
    loop._rewrite_fn = lambda *a, **k: "x"  # would-be active rewriter
    loop._run_self_rewrite()
    assert proposed == []  # rewrite skipped because rollback fired


def test_rewrite_runs_when_no_rollback(tmp_path, monkeypatch):
    # Control: with no rollback and a rewrite_fn set, the gate is consulted.
    monkeypatch.setattr("src.agent.quality.collector.collect_outcomes",
                        lambda journal: [])
    monkeypatch.setattr("src.agent.learning.self_rewrite.maybe_rollback",
                        lambda hist, ver_excess: False)  # no rollback
    consulted = []
    monkeypatch.setattr("src.agent.learning.self_rewrite.should_rewrite",
                        lambda hist, sample, **k: consulted.append(sample) or False)
    monkeypatch.setattr("src.agent.learning.self_rewrite.save_history", lambda *a, **k: None)

    loop = _loop(tmp_path)
    loop._rewrite_fn = lambda *a, **k: "x"
    loop._run_self_rewrite()
    assert consulted == [0]  # should_rewrite consulted (empty outcomes → sample 0)
