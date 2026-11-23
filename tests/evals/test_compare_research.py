"""Comparison experiments must preserve pairing, all-call cost, and isolation."""

import json
import subprocess
from pathlib import Path

import pytest

from src.evals.compare_research import MeasuredRunner, call_totals, run_comparison, summarize
from src.evals.scenario import Expectation, Scenario, save_scenario
from src.evals.profiles import ResearchProfile


def _case(tmp_path):
    path = tmp_path / "case.json"
    save_scenario(Scenario(
        id="quiet", turn_type="research", universe=["ALFA"],
        brief="Frozen market: no opportunity; cash account.",
        expectation=Expectation(no_churn=True),
    ), path)
    return path


def _runner(cmd, *, input, cwd, timeout, env=None):
    assert "--safe-mode" in cmd
    assert cmd[cmd.index("--tools") + 1] == "Bash,Read,Write,Edit,Glob,Grep"
    assert "--strict-mcp-config" in cmd
    assert Path(cwd).is_relative_to(Path("/tmp"))
    assert env["AGENT_JOURNAL_ROOT"] == cwd
    assert "AUTOSTOCK_TOOLS_FIXTURE_DIR" in env
    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({
        "result": "No action justified.", "session_id": "test", "is_error": False,
        "usage": {"input_tokens": 10, "output_tokens": 5,
                  "cache_read_input_tokens": 2, "cache_creation_input_tokens": 3},
        "total_cost_usd": 0.01, "modelUsage": {"test-model": {}},
    }))


def test_paired_modes_record_every_call_and_sequential_context(tmp_path):
    calls = []
    session_costs = {}
    def capture(cmd, **kwargs):
        calls.append((cmd, kwargs["input"]))
        proc = _runner(cmd, **kwargs)
        flag = "--resume" if "--resume" in cmd else "--session-id"
        session = cmd[cmd.index(flag) + 1]
        session_costs[session] = session_costs.get(session, 0) + 0.01
        payload = json.loads(proc.stdout)
        payload["total_cost_usd"] = session_costs[session]
        proc.stdout = json.dumps(payload)
        return proc
    directory = run_comparison([_case(tmp_path)], model="test-model", runner=capture,
                               output_root=tmp_path / "results", repeats=1)
    rows = [json.loads(p.read_text()) for p in (directory / "runs").glob("*.json")]
    by_mode = {r["mode"]: r for r in rows}
    assert set(by_mode) == {"single", "sequential", "parallel"}
    assert by_mode["single"]["metrics"]["calls"] == 1
    for mode in ("sequential", "parallel"):
        assert by_mode[mode]["metrics"]["calls"] == 3
        assert by_mode[mode]["metrics"]["input_tokens"] == 30
        assert by_mode[mode]["metrics"]["reported_cost_usd"] == pytest.approx(0.03)
    for cmd, prompt in calls:
        if "Cross-validation round" in prompt or "Final synthesis round" in prompt:
            assert "--resume" in cmd  # review actually sees the earlier research
    assert (directory / "summary.csv").exists()
    assert directory.name in (directory.parent / "README.md").read_text()
    assert "single" in summarize(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["runner"] == "injected_test_runner"
    assert manifest["source_sha256"]["src/agent/prompts.py"]
    assert manifest["source_sha256"]["main.py"]  # production risk construction is part of replay
    assert manifest["source_sha256"]["pyproject.toml"]
    assert manifest["runtime"]["python"]


def test_errors_saved_and_counted_in_summary(tmp_path):
    def broken(*args, **kwargs):
        raise RuntimeError("injected unavailable model")
    directory = run_comparison([_case(tmp_path)], model="test", runner=broken,
                               modes=("single",), output_root=tmp_path / "results")
    row = json.loads(next((directory / "runs").glob("*.json")).read_text())
    assert "unavailable model" in row["error"]
    assert row["metrics"]["failed_calls"] == 1
    assert row["metrics"]["input_tokens"] is None
    assert "0 / 1" in summarize(directory)


def test_partial_usage_is_unknown_not_underreported():
    measured = MeasuredRunner()
    measured.calls = [{"usage": {"input_tokens": 50}}, {"usage": {}}]
    assert measured.totals()["input_tokens"] is None


def test_session_cost_is_counted_once_while_turn_tokens_are_summed():
    calls = [
        {"session_id": "shared", "reported_cost_usd": cost, "usage": {"input_tokens": 10}}
        for cost in (0.1, 0.15, 0.2)
    ]
    calls.append({"session_id": "other", "reported_cost_usd": 0.1, "usage": {"input_tokens": 5}})
    assert call_totals(calls)["reported_cost_usd"] == pytest.approx(0.3)
    assert call_totals(calls)["input_tokens"] == 35
    calls.append({"session_id": "shared", "reported_cost_usd": 0})
    assert call_totals(calls)["reported_cost_usd"] is None  # crashed/reset totals are unknown


def test_old_sequential_artifact_cost_can_be_corrected_without_model_calls():
    calls = [{"reported_cost_usd": value} for value in (0.1, 0.15, 0.2)]
    assert call_totals(calls, mode="sequential")["reported_cost_usd"] == 0.2
    assert call_totals(calls, mode="parallel")["reported_cost_usd"] == pytest.approx(0.45)


def test_tool_denial_is_visible_without_becoming_a_model_failure(tmp_path):
    def denied(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({
            "result": "Used supplied brief instead.", "is_error": False,
            "permission_denials": [{"tool_name": "Bash", "tool_use_id": "blocked"}],
        }))
    measured = MeasuredRunner(denied)
    measured(["claude", "--model", "test"], input="research", cwd=str(tmp_path), timeout=1)
    assert measured.totals()["permission_denials"] == 1
    assert measured.totals()["failed_calls"] == 0


def test_interrupted_comparison_keeps_partial_run_as_error(tmp_path):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_comparison([_case(tmp_path)], model="test", runner=interrupted,
                       modes=("single",), output_root=tmp_path / "results")
    directory, = (p for p in (tmp_path / "results").iterdir() if p.is_dir())
    row = json.loads(next((directory / "runs").glob("*.json")).read_text())
    assert "KeyboardInterrupt" in row["error"]
    assert row["metrics"]["failed_calls"] == 1
    assert "0 / 1" in summarize(directory)


def test_matrix_pairs_prompt_model_effort_and_freezes_exact_inputs(tmp_path):
    seen = []
    def capture(cmd, **kw):
        seen.append((cmd, kw["input"], kw["env"]["CLAUDE_CODE_EFFORT_LEVEL"]))
        return _runner(cmd, **kw)
    profiles = [ResearchProfile(name="current", model="test-model", effort="medium"),
                ResearchProfile(name="previous", model="test-model", effort="high",
                                prompt_ref="baseline:pre-frontier")]
    directory = run_comparison([_case(tmp_path)], profiles=profiles, modes=("single",),
                               repeats=2, runner=capture, output_root=tmp_path / "results")
    rows = [json.loads(p.read_text()) for p in (directory / "runs").glob("*.json")]
    assert {(r["profile"], r["repeat"]) for r in rows} == {
        (profile, repeat) for profile in ("current", "previous") for repeat in (0, 1)}
    assert all(r.get("decisions_sha256") and r.get("finished_at") for r in rows)
    assert {effort for _, _, effort in seen} == {"medium", "high"}
    assert all(("## Decision standard" in prompt) == (effort == "medium") for _, prompt, effort in seen)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert len(manifest["prompt_snapshots"]) == 2
    frozen = json.loads(next((directory / "scenarios").glob("*.json")).read_text())
    assert frozen["risk"]["max_position_pct"] == .05


def test_request_costs_remain_additive_even_with_sequential_mode():
    calls = [{"cost_scope":"request", "reported_cost_usd":v} for v in (.1,.2)]
    assert call_totals(calls,mode="sequential")["reported_cost_usd"] == pytest.approx(.3)
