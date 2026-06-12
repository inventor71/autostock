"""F41 — per-turn multi-agent evaluation reports + orchestrator capture."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from src.agent import reports
from src.agent.journal import Journal
from src.agent.orchestrator import AgentTradingLoop, SubAgentReport, SubAgentTask
from src.agent.session import AgentSession


# -- module: reports schema ------------------------------------------- #

class TestAgentReportsModule:
    def test_roundtrip_by_turn_id(self, tmp_path):
        report = reports.build_report(
            turn_id="R5", ts="2026-06-02T21:42:52+09:00", mode="sequential",
            agents=[reports.make_eval(index=0, label="Round 1 · Initial",
                                            role="initial", text="lean HOLD AAPL")],
            synthesis_text="final: HOLD AAPL",
        )
        path = reports.write_agent_report(tmp_path, report)
        assert path is not None and path.name == "R5.json"
        back = reports.read_agent_report(tmp_path, "R5")
        assert back is not None
        assert back["mode"] == "sequential"
        assert back["n_agents"] == 1
        assert back["agents"][0]["text"] == "lean HOLD AAPL"
        assert back["synthesis"]["text"] == "final: HOLD AAPL"
        assert back["et_date"] == "2026-06-02"
        assert reports.has_agent_report(tmp_path, "R5")

    def test_ts_key_fallback_when_turn_id_blank(self, tmp_path):
        report = reports.build_report(
            turn_id="", ts="2026-06-02T21:42:52+09:00", mode="parallel",
            agents=[], synthesis_text="x",
        )
        path = reports.write_agent_report(tmp_path, report)
        assert path is not None
        assert ":" not in path.name  # ts colons sanitized
        # blank turn_id cannot be looked up by id
        assert reports.read_agent_report(tmp_path, "") is None
        assert reports.has_agent_report(tmp_path, "") is False

    def test_read_missing_returns_none(self, tmp_path):
        assert reports.read_agent_report(tmp_path, "NOPE") is None
        assert reports.has_agent_report(tmp_path, "NOPE") is False

    def test_write_is_atomic_no_tmp_left(self, tmp_path):
        report = reports.build_report(
            turn_id="R1", ts="2026-06-02T10:00:00+09:00", mode="sequential",
            agents=[], synthesis_text="s",
        )
        reports.write_agent_report(tmp_path, report)
        d = reports.reports_dir(tmp_path)
        assert not list(d.glob("*.tmp"))

    def test_text_not_truncated(self, tmp_path):
        long_text = "x" * 50_000
        report = reports.build_report(
            turn_id="R1", ts="2026-06-02T10:00:00+09:00", mode="sequential",
            agents=[reports.make_eval(index=0, label="a", role="b", text=long_text)],
            synthesis_text="s",
        )
        reports.write_agent_report(tmp_path, report)
        back = reports.read_agent_report(tmp_path, "R1")
        assert len(back["agents"][0]["text"]) == 50_000


# -- orchestrator capture --------------------------------------------------- #

def _fake_runner(decisions_to_write=None, result_text="ok",
                 write_on_keywords=("Final synthesis",)):
    call_count = [0]

    def runner(cmd, *, input, cwd, timeout, env=None):
        call_count[0] += 1
        prompt_lower = (input or "").lower()
        if decisions_to_write and any(kw.lower() in prompt_lower for kw in write_on_keywords):
            with (Path(cwd) / "decisions.jsonl").open("a") as f:
                for d in decisions_to_write:
                    f.write(json.dumps(d) + "\n")
        return subprocess.CompletedProcess(
            cmd, 0,
            stdout=json.dumps({"result": result_text, "session_id": "t", "is_error": False}),
            stderr="",
        )
    return runner, call_count


class TestSequentialCapture:
    def test_persists_rounds_and_fixes_summary(self, tmp_path):
        decisions = [{"ts": "2026-06-01T09:00:00", "symbol": "AAPL", "action": "BUY",
                      "stop": 140.0, "reason": "test"}]
        runner, calls = _fake_runner(decisions_to_write=decisions,
                                     write_on_keywords=("Final synthesis",))
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL", "MSFT"],
            multi_agent_enabled=True, multi_agent_mode="sequential", multi_agent_n=3,
            research_timeout=600,
        )
        loop.run_morning_research()
        assert calls[0] == 3  # initial + 1 debate + synthesis

        # FR-2: turn record now has a non-empty turn_id and summary.
        rows = [json.loads(l) for l in (tmp_path / "turns.jsonl").read_text().splitlines() if l]
        assert rows[-1]["turn_id"]
        assert rows[-1]["summary"]
        assert "AAPL" in rows[-1]["summary"]

        # FR-1: agent report persisted; agents = non-synthesis rounds.
        report = reports.read_agent_report(tmp_path, rows[-1]["turn_id"])
        assert report is not None
        assert report["mode"] == "sequential"
        assert [a["label"] for a in report["agents"]] == ["Round 1 · Initial", "Round 2 · Debate"]
        assert report["synthesis"]["text"]

        # FR-1: new decisions tagged with the turn_id.
        assert loop.last_new_decisions[0].turn_id == rows[-1]["turn_id"]

    def test_n2_has_only_initial_round(self, tmp_path):
        runner, calls = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_mode="sequential", multi_agent_n=2,
            research_timeout=600,
        )
        loop.run_morning_research()
        assert calls[0] == 2  # initial + synthesis, no debate
        report = reports.read_agent_report(tmp_path, loop.last_turn_id)
        assert [a["label"] for a in report["agents"]] == ["Round 1 · Initial"]


class TestParallelCapture:
    def test_persists_sub_agents(self, tmp_path):
        Journal(tmp_path).init()
        (tmp_path / "positions").mkdir(exist_ok=True)
        decisions = [{"ts": "2026-06-01T09:00:00", "symbol": "AAPL", "action": "HOLD",
                      "stop": 140.0, "reason": "test"}]
        runner, _ = _fake_runner(decisions_to_write=decisions, write_on_keywords=("synthesis",))
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL", "MSFT"],
            multi_agent_enabled=True, multi_agent_mode="parallel", multi_agent_n=3,
            research_timeout=600,
        )
        loop.run_morning_research()
        report = reports.read_agent_report(tmp_path, loop.last_turn_id)
        assert report is not None
        assert report["mode"] == "parallel"
        assert report["n_agents"] >= 2
        assert all(a["status"] == "ok" for a in report["agents"])
        assert all(a["label"].startswith("Agent ") for a in report["agents"])

    def test_failed_sub_agents_recorded_as_error(self, tmp_path):
        Journal(tmp_path).init()
        (tmp_path / "positions").mkdir(exist_ok=True)
        decisions = [{"ts": "2026-06-01T09:00:00", "symbol": "AAPL", "action": "BUY",
                      "stop": 140.0, "reason": "ok"}]
        runner, _ = _fake_runner(decisions_to_write=decisions,
                                 write_on_keywords=("synthesis",))
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_mode="parallel", multi_agent_n=3,
            research_timeout=600,
        )

        real_sub = loop._run_sub_agent

        def _one_fails(task, ws, timeout, signal_brief=None):
            if task.agent_index == 0:
                return SubAgentReport(task.agent_index, task, "", False, "injected failure")
            return real_sub(task, ws, timeout, signal_brief)

        loop._run_sub_agent = _one_fails  # type: ignore[assignment]
        loop.run_morning_research()
        report = reports.read_agent_report(tmp_path, loop.last_turn_id)
        statuses = {a["index"]: a["status"] for a in report["agents"]}
        assert statuses.get(0) == "error"


class TestBestEffort:
    def test_report_write_failure_does_not_break_turn(self, tmp_path, monkeypatch):
        runner, _ = _fake_runner()
        session = AgentSession(workspace=tmp_path, runner=runner, session_date=date(2026, 6, 1))
        loop = AgentTradingLoop(
            session=session, universe=["AAPL"],
            multi_agent_enabled=True, multi_agent_mode="sequential", multi_agent_n=2,
            research_timeout=600,
        )
        monkeypatch.setattr(
            "src.agent.reports.os.replace",
            lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
        )
        # Turn must still complete and record telemetry.
        result = loop.run_morning_research()
        assert result is not None
        rows = [json.loads(l) for l in (tmp_path / "turns.jsonl").read_text().splitlines() if l]
        assert rows[-1]["turn_id"]
