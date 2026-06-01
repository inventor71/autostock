"""Tests for F23 multi-agent research orchestration."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agent.journal import Journal, LessonRecord
from src.agent.orchestrator import AgentTradingLoop, SubAgentTask
from src.agent.session import AgentSession, AgentTurnResult
from src.agent import prompts


# -- helpers ---------------------------------------------------------------- #

def _fake_runner(decisions_to_write: list[dict] | None = None, result_text: str = "ok",
                  write_on_keywords: tuple[str, ...] = ("synthesis", "final", "Analyst")):
    """Build a runner that simulates claude -p: optionally writes decisions."""
    call_count = [0]

    def runner(cmd, *, input, cwd, timeout, env=None):
        call_count[0] += 1
        prompt_lower = (input or "").lower()
        if decisions_to_write and any(kw.lower() in prompt_lower for kw in write_on_keywords):
            dec_file = Path(cwd) / "decisions.jsonl"
            with dec_file.open("a") as f:
                for d in decisions_to_write:
                    f.write(json.dumps(d) + "\n")
        return subprocess.CompletedProcess(
            cmd, 0,
            stdout=json.dumps({"result": result_text, "session_id": "test-123", "is_error": False}),
            stderr="",
        )
    return runner, call_count


# -- AgentSession one_shot ------------------------------------------------- #

class TestOneShot:
    def test_one_shot_no_state_file(self, tmp_path):
        runner, _ = _fake_runner()
        s = AgentSession(workspace=tmp_path, one_shot=True, runner=runner, session_date=date(2026, 6, 1))
        s.run_turn("test prompt")
        state_dir = tmp_path / ".sessions"
        assert not state_dir.exists() or not list(state_dir.iterdir())

    def test_normal_creates_state_file(self, tmp_path):
        runner, _ = _fake_runner()
        s = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        s.run_turn("test prompt")
        state_file = tmp_path / ".sessions" / "2026-06-01.json"
        assert state_file.exists()

    def test_create_sub_agent_is_one_shot(self, tmp_path):
        sub = AgentSession.create_sub_agent(workspace=tmp_path)
        assert sub._one_shot is True
        assert "Write" not in sub.allowed_tools
        assert "Edit" not in sub.allowed_tools
        assert "Read" in sub.allowed_tools

    def test_sub_agent_env_override(self, tmp_path):
        captured_env = {}
        def spy_runner(cmd, *, input, cwd, timeout, env=None):
            captured_env.update(env or {})
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"result": "ok", "session_id": "x"}), stderr="",
            )
        sub = AgentSession.create_sub_agent(workspace=tmp_path, runner=spy_runner)
        sub.run_turn("test")
        assert captured_env.get("AGENT_JOURNAL_ROOT") == str(tmp_path)


# -- Prompts ---------------------------------------------------------------- #

class TestMultiAgentPrompts:
    def test_initial_prompt_contains_signals(self):
        p = prompts.multi_research_initial_prompt(
            ["AAPL"], held=["AAPL"], signals=["earnings", "macro"], n_rounds=2,
        )
        assert "earnings" in p
        assert "macro" in p
        assert "decisions.jsonl" in p
        assert "Do NOT write" in p

    def test_debate_prompt(self):
        p = prompts.debate_prompt(1, 3)
        assert "round 2 of 4" in p
        assert "Do NOT write" in p

    def test_synthesis_prompt(self):
        p = prompts.synthesis_prompt(3)
        assert "Verdict" in p
        assert "decisions.jsonl" in p

    def test_sub_agent_prompt(self):
        p = prompts.sub_agent_prompt("Review AAPL", ["AAPL", "MSFT"], ["indicators"])
        assert "AAPL" in p
        assert "Verdict" in p
        assert "Do NOT write to decisions" in p

    def test_parallel_synthesis_prompt(self):
        p = prompts.parallel_synthesis_prompt(["report 1 text", "report 2 text"])
        assert "Analyst 1" in p
        assert "Analyst 2" in p
        assert "Verdict" in p

    def test_lesson_context(self):
        lessons = [LessonRecord(lesson_id="L001", category="sizing", takeaway="Size down")]
        ctx = prompts._build_lesson_context(lessons)
        assert "Size down" in ctx
        assert "sizing" in ctx

    def test_lesson_context_empty(self):
        assert prompts._build_lesson_context([]) == ""


# -- Sequential Research (Mode B) ------------------------------------------ #

class TestSequentialResearch:
    def test_mode_b_3_rounds(self, tmp_path):
        decisions = [
            {"ts": "2026-06-01T09:00:00", "symbol": "AAPL", "action": "BUY",
             "stop": 140.0, "reason": "test"},
        ]
        runner, call_count = _fake_runner(
            decisions_to_write=decisions,
            write_on_keywords=("Final synthesis",),
        )
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL", "MSFT"],
            multi_agent_enabled=True, multi_agent_mode="sequential", multi_agent_n=3,
            research_timeout=600,
        )
        result = loop.run_morning_research()
        assert call_count[0] == 3  # initial + 1 debate + synthesis
        assert len(loop.last_new_decisions) == 1
        assert loop.last_kept[0].symbol == "AAPL"

    def test_mode_b_n2_minimal(self, tmp_path):
        runner, call_count = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_mode="sequential", multi_agent_n=2,
            research_timeout=600,
        )
        loop.run_morning_research()
        assert call_count[0] == 2  # initial + synthesis (0 debate rounds)


# -- Parallel Research (Mode C) -------------------------------------------- #

class TestParallelResearch:
    def test_mode_c_creates_isolated_workspace(self, tmp_path):
        Journal(tmp_path).init()
        (tmp_path / "regime.md").write_text("bull")
        (tmp_path / "positions").mkdir(exist_ok=True)
        (tmp_path / "positions" / "AAPL.md").write_text("long AAPL")

        decisions = [
            {"ts": "2026-06-01T09:00:00", "symbol": "AAPL", "action": "HOLD",
             "stop": 140.0, "reason": "test"},
        ]
        runner, call_count = _fake_runner(decisions_to_write=decisions)
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL", "MSFT"],
            multi_agent_enabled=True, multi_agent_mode="parallel", multi_agent_n=3,
            research_timeout=600,
        )
        result = loop.run_morning_research()
        assert len(loop.last_new_decisions) == 1
        # sub-agents + synthesis = 3 calls (2 sub + 1 synthesis)
        assert call_count[0] >= 3

    def test_mode_c_no_decisions_fallback(self, tmp_path):
        """When all sub-agents fail, fall back to single-session research."""
        decisions = [
            {"ts": "2026-06-01T09:00:00", "symbol": "AAPL", "action": "BUY",
             "stop": 140.0, "reason": "fallback"},
        ]
        runner, call_count = _fake_runner(
            decisions_to_write=decisions,
            write_on_keywords=("research", "morning", "synthesis"),
        )
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_mode="parallel", multi_agent_n=3,
            research_timeout=600,
        )
        # Sub-agents always fail → fallback path fires
        def _fail_sub(task, ws, timeout):
            from src.agent.orchestrator import SubAgentReport
            return SubAgentReport(task.agent_index, task, "", False, "injected failure")
        loop._run_sub_agent = _fail_sub  # type: ignore[assignment]
        result = loop.run_morning_research()
        assert isinstance(result, AgentTurnResult)
        assert len(loop.last_new_decisions) == 1
        assert loop.last_kept[0].symbol == "AAPL"


# -- Disabled / Fallback --------------------------------------------------- #

class TestDisabledFallback:
    def test_disabled_uses_single_session(self, tmp_path):
        runner, call_count = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=False,
            research_timeout=600,
        )
        loop.run_morning_research()
        assert call_count[0] == 1

    def test_n1_falls_back(self, tmp_path):
        runner, call_count = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_n=1,
            research_timeout=600,
        )
        loop.run_morning_research()
        assert call_count[0] == 1  # single session fallback


# -- Timeout resolution ---------------------------------------------------- #

class TestTimeoutResolution:
    def test_auto_timeout(self):
        from config.config import AgentConfig
        cfg = AgentConfig(research_start_before_open=60, research_end_before_open=5)
        auto = (cfg.research_start_before_open - cfg.research_end_before_open) * 60
        assert auto == 3300

    def test_explicit_override(self):
        from config.config import AgentConfig
        cfg = AgentConfig(research_timeout=2400.0)
        assert cfg.research_timeout == 2400.0


# -- SubAgentTask ---------------------------------------------------------- #

class TestSubAgentTask:
    def test_plan_sub_tasks_n3(self, tmp_path):
        runner, _ = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner)
        loop = AgentTradingLoop(
            session=session, universe=["AAPL", "MSFT"],
            multi_agent_enabled=True, multi_agent_n=3,
        )
        tasks = loop._plan_sub_tasks()
        assert len(tasks) == 2
        assert tasks[0].agent_index == 0
        assert tasks[1].agent_index == 1

    def test_plan_sub_tasks_n2(self, tmp_path):
        runner, _ = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner)
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_n=2,
        )
        tasks = loop._plan_sub_tasks()
        assert len(tasks) == 1
