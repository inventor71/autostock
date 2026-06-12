"""Tier-1 grading: behavior-match invariants (PBT-03) + real-executor replay."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.journal import Decision
from src.evals.grading import behavior_grade, replay_through_executor
from src.evals.scenario import Expectation, Scenario
from tests.evals import generators as gen

decisions = st.builds(
    Decision,
    symbol=gen.symbols,
    action=gen.actions,
    reason=st.text(max_size=20),
    lessons_cited=st.lists(st.from_regex(r"L\d{1,3}", fullmatch=True), max_size=2),
)


class TestBehaviorGrade:
    @settings(max_examples=60)
    @given(ds=st.lists(decisions, max_size=5),
           expectation=st.builds(Expectation, no_churn=st.just(True),
                                 focus_symbol=st.one_of(st.none(), gen.symbols)))
    def test_no_churn_invariant(self, ds, expectation):
        """PBT-03: under no_churn, matched <=> every relevant decision is HOLD."""
        relevant = [d for d in ds if expectation.focus_symbol is None
                    or d.symbol == expectation.focus_symbol]
        expected = all(d.action == "HOLD" for d in relevant)
        assert behavior_grade(ds, expectation)["matched"] == expected

    @settings(max_examples=60)
    @given(ds=st.lists(decisions, max_size=5),
           allowed=st.lists(gen.actions, min_size=1, max_size=3, unique=True))
    def test_allowed_actions_invariant(self, ds, allowed):
        """PBT-03: matched <=> some relevant decision uses an allowed action —
        an action outside the set can never satisfy the expectation."""
        expectation = Expectation(allowed_actions=allowed)
        expected = any(d.action in allowed for d in ds)
        assert behavior_grade(ds, expectation)["matched"] == expected

    def test_lessons_cited_rate(self):
        ds = [Decision(symbol="AAPL", action="HOLD", lessons_cited=["L1"]),
              Decision(symbol="MSFT", action="HOLD")]
        grade = behavior_grade(ds, Expectation(no_churn=True))
        assert grade["lessons_cited_rate"] == 0.5


class TestExecutorReplay:
    """Statuses come from the REAL DecisionExecutor — these tests prove the
    production gates fire inside the replay, not a re-implementation."""

    def _scenario(self, **kw) -> Scenario:
        base = dict(id="t", turn_type="intraday", universe=["AAPL"],
                    prices={"AAPL": 100.0}, expectation=Expectation(no_churn=True))
        base.update(kw)
        return Scenario(**base)

    def test_out_of_universe_rejected(self, tmp_path):
        out = replay_through_executor(
            self._scenario(), [Decision(symbol="NVDA", action="BUY", stop=90.0)],
            journal_root=tmp_path)
        assert out[0]["status"] == "skipped_out_of_universe"

    def test_hold_without_position_skips(self, tmp_path):
        out = replay_through_executor(
            self._scenario(), [Decision(symbol="AAPL", action="HOLD")],
            journal_root=tmp_path)
        assert out[0]["status"] == "skipped_hold"

    def test_buy_with_stop_reaches_broker(self, tmp_path):
        out = replay_through_executor(
            self._scenario(), [Decision(symbol="AAPL", action="BUY", stop=95.0,
                                        target=120.0, confidence=0.7)],
            journal_root=tmp_path)
        assert out[0]["status"] in ("executed", "no_order")  # sizing may zero out
        assert out[0]["status"] == "executed"

    def test_short_cover_on_seeded_short_executes(self, tmp_path):
        """A short position seeded from the scenario is visible to the real
        executor: covering it routes through RiskManager -> SimulatedBroker."""
        scenario = self._scenario(
            held={"AAPL": {"qty": 10, "avg_entry_price": 110.0, "side": "short"}})
        out = replay_through_executor(
            scenario, [Decision(symbol="AAPL", action="BUY_TO_COVER")],
            journal_root=tmp_path)
        assert out[0]["status"] == "executed"

    def test_hold_with_stop_places_protection(self, tmp_path):
        scenario = self._scenario(
            held={"AAPL": {"qty": 10, "avg_entry_price": 90.0, "side": "long"}})
        out = replay_through_executor(
            scenario, [Decision(symbol="AAPL", action="HOLD", stop=95.0)],
            journal_root=tmp_path)
        assert out[0]["status"] == "executed"
        assert "protect" in out[0]["detail"]

    def test_replay_logs_into_sandbox_journal(self, tmp_path):
        """Isolation: the execution log lands in the given journal root, not in
        the repo's default workspace/ journal (executor's default)."""
        out = replay_through_executor(
            self._scenario(),
            [Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0)],
            journal_root=tmp_path)
        assert out[0]["status"] == "executed"
        assert (tmp_path / "execution_log.jsonl").exists()
