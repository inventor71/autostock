"""Provider contracts: effort, complete output, tool isolation, and continuation."""

import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from config.config import AgentConfig, _apply_env_overrides
from src.agent.openai_session import OpenAIAgentSession
from src.agent.session import AgentSession
from src.strategy.llm.client import ClaudeClient, OpenAIClient


class Response(SimpleNamespace):
    def model_dump(self, **kwargs):
        return {"model": self.model, "usage": {"input_tokens": 10, "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 2}},
                "status": self.status, "id": self.id}


def response(**kwargs):
    fields = dict(id="resp_1", model="gpt-6-astra", status="completed", output_text="Hold.",
                  output=[], usage=SimpleNamespace(model_dump=lambda: {"output_tokens": 5}))
    fields.update(kwargs)
    return Response(**fields)


def client_responses(items):
    calls = []
    iterator = iter(items)
    def create(**kwargs):
        calls.append(kwargs)
        return next(iterator)
    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def test_explicit_cli_effort_wins_over_shell_and_resumed_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_EFFORT_LEVEL", "max")
    calls = []
    def runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": "Done"}))
    session = AgentSession(workspace=tmp_path, effort="medium", runner=runner)
    research = session.run_turn("Research", model="claude-fable-5-2", effort="high")
    session.run_turn("Monitor")
    assert [kw["env"]["CLAUDE_CODE_EFFORT_LEVEL"] for _, kw in calls] == ["high", "medium"]
    assert "--resume" in calls[1][0]
    assert research.raw["autostock_request"]["effort"] == "high"
    assert os.environ["CLAUDE_CODE_EFFORT_LEVEL"] == "max"


def test_instance_model_overrides_are_validated(monkeypatch):
    monkeypatch.setenv("AUTOSTOCK_RESEARCH_MODEL", "claude-fable-5-2")
    monkeypatch.setenv("AUTOSTOCK_RESEARCH_EFFORT", "max")
    cfg = {}
    _apply_env_overrides(cfg)
    assert AgentConfig(**cfg["agent"]).research_effort == "max"
    with pytest.raises(ValueError):
        AgentConfig(research_effort="ultrathink")


def test_openai_completion_uses_responses_reasoning_without_temperature(monkeypatch):
    api, calls = client_responses([response(output_text='{"signal":"HOLD"}')])
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: api)
    client = OpenAIClient(api_key="test", reasoning_effort="max")
    assert client.complete("standard", "evidence") == '{"signal":"HOLD"}'
    assert calls[0]["reasoning"] == {"effort": "max"}
    assert calls[0]["max_output_tokens"] == 32768
    assert "temperature" not in calls[0] and "max_tokens" not in calls[0]
    assert calls[0]["store"] is False


def test_partial_openai_output_is_never_an_executable_completion(monkeypatch):
    api, calls = client_responses([response(status="incomplete", output_text='{"signal":"BUY"}')])
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: api)
    with pytest.raises(ValueError, match="incomplete"):
        OpenAIClient(api_key="test").complete("standard", "evidence")
    assert len(calls) == 1  # no expensive retry of incomplete model output


def test_legacy_openai_override_keeps_nonreasoning_temperature(monkeypatch):
    api, calls = client_responses([response()])
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: api)
    OpenAIClient(api_key="test", model="gpt-4o", temperature=.2).complete("s", "u")
    assert calls[0]["temperature"] == .2 and "reasoning" not in calls[0]


def test_claude_adaptive_response_extracts_text_after_thinking(monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(model="claude-sonnet-5-5", stop_reason="end_turn",
            usage=SimpleNamespace(model_dump=lambda: {}), content=[
                SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text='{"signal":"HOLD"}')])
    monkeypatch.setattr("anthropic.Anthropic", lambda **kwargs:
                        SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert "HOLD" in ClaudeClient(api_key="test").complete("s", "u")
    assert calls[0]["output_config"] == {"effort": "high"}
    assert calls[0]["thinking"] == {"type": "adaptive"}
    assert "temperature" not in calls[0]


def test_openai_tool_loop_continuity_and_journal_permissions(tmp_path):
    call = SimpleNamespace(type="function_call", name="write_file", call_id="tool_1",
                           arguments=json.dumps({"path": "decisions.jsonl", "append": True,
                                                 "content": '{"symbol":"X","action":"HOLD"}\n'}))
    api, calls = client_responses([response(output=[call], output_text=""),
                                   response(id="resp_2"), response(id="resp_3")])
    events = []
    session = OpenAIAgentSession(tmp_path, client=api, observer=events.append, allow_web=False)
    first = session.run_turn("research", effort="max")
    second = session.run_turn("followup", effort="medium")
    assert len(session.journal.read_decisions()) == 1
    assert calls[1]["previous_response_id"] == "resp_1"
    assert calls[1]["input"][0]["call_id"] == "tool_1"
    assert calls[2]["previous_response_id"] == "resp_2"
    assert calls[2]["reasoning"]["effort"] == "medium"
    assert first.raw["usage"]["output_tokens"] == 10
    assert second.resumed and len(events) == 3
    assert all(t["type"] != "web_search" for t in calls[0]["tools"])
    sub = session.create_sub_agent(tmp_path / "sub", effort="high")
    assert sub.read_only and sub.client is api
    with pytest.raises(ValueError, match="Analysts"):
        sub._tool("write_file", {"path":"decisions.jsonl", "content":"x", "append":True}, 1e20)
    with pytest.raises(ValueError, match="inside"):
        session._tool("read_file", {"path":"../secret.txt"}, 1e20)
    with pytest.raises(ValueError, match="read-only"):
        session._tool("market_data", {"arguments":["trigger", "register"]}, 1e20)


def test_openai_failed_request_is_recorded_without_advancing_session(tmp_path):
    api, calls = client_responses([response(status="incomplete")])
    events = []
    session = OpenAIAgentSession(tmp_path, client=api, observer=events.append)
    with pytest.raises(RuntimeError, match="incomplete"):
        session.run_turn("research")
    assert session.session_id is None and events[0]["is_error"]


def test_incomplete_agent_turn_discards_previously_staged_decisions(tmp_path):
    write = SimpleNamespace(type="function_call",name="write_file",call_id="w1",arguments=json.dumps({
        "path":"decisions.jsonl","append":True,"content":'{"symbol":"X","action":"BUY"}\n'}))
    read = SimpleNamespace(type="function_call",name="read_file",call_id="r1",
                           arguments='{"path":"decisions.jsonl"}')
    api,calls=client_responses([response(output=[write]),response(output=[read]),response(status="incomplete")])
    session=OpenAIAgentSession(tmp_path,client=api)
    with pytest.raises(RuntimeError,match="incomplete"):
        session.run_turn("research")
    assert '"BUY"' in calls[2]["input"][0]["output"]  # read-your-writes inside the turn
    assert session.journal.read_decisions() == []
    assert session.session_id is None


def test_openai_fixture_tools_do_not_fall_back_to_live_data(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "quote.json").write_text('{"X":{"price":123}}')
    monkeypatch.setenv("AUTOSTOCK_TOOLS_FIXTURE_DIR", str(fixture))
    api, _ = client_responses([])
    session = OpenAIAgentSession(tmp_path / "ws", client=api)
    session.journal.init()
    result = session._tool("market_data", {"arguments":["quote", "X"]}, 1e20)
    assert json.loads(result)["price"] == 123
    missing = session._tool("market_data", {"arguments":["quote", "MISSING"]}, 1e20)
    assert json.loads(missing)["error"] == "fixture_missing"
    assert all(t["type"] != "web_search" for t in session._tools())


def test_openai_comparison_uses_production_single_sequential_and_parallel_paths(tmp_path):
    from src.evals.compare_research import run_comparison
    from src.evals.profiles import ResearchProfile
    from src.evals.scenario import Scenario, Expectation, save_scenario

    source = tmp_path / "case.json"
    save_scenario(Scenario(id="api",turn_type="research",universe=["X"],
                           expectation=Expectation(no_churn=True)), source)
    api, calls = client_responses([response(id=f"r{i}") for i in range(7)])
    directory = run_comparison([source],profiles=[ResearchProfile(
        name="astra", provider="openai", model="gpt-6-astra", effort="max")],
        api_client=api, output_root=tmp_path / "results")
    rows=[json.loads(p.read_text()) for p in (directory / "runs").glob("*.json")]
    assert {r["mode"]:r["metrics"]["calls"] for r in rows} == {
        "single":1,"sequential":3,"parallel":3}
    assert all(not r.get("error") for r in rows)
    assert all(r["metrics"]["reported_cost_usd"] is None for r in rows)
    assert len(calls) == 7
    assert all(c["reasoning"] == {"effort":"max"} for c in calls)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["runner"] == "injected_test_runner"
    assert "cli_version" not in manifest  # API experiments never invoke Claude


def test_health_checks_agent_model_access_without_paid_generations(monkeypatch):
    from src.monitoring.health.dimensions.llm import LLMChecker
    from src.monitoring.health.report import CheckStatus

    seen = []
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs:
                        SimpleNamespace(models=SimpleNamespace(retrieve=seen.append)))
    settings = SimpleNamespace(
        llm=SimpleNamespace(provider="claude_code", model=None),
        agent=AgentConfig(provider="openai", model="gpt-6-astra", research_model="gpt-6-astra"),
        openai_api_key="test",
    )
    checker = LLMChecker(settings)
    checker._check_claude_cli = lambda: SimpleNamespace(name="claude_cli")
    checker._check_cost = lambda: SimpleNamespace(name="turn_cost")
    results = {r.name: r for r in checker.check()}
    assert seen == ["gpt-6-astra"]
    assert results["openai_api"].status == CheckStatus.OK
    assert "generation not tested" in results["openai_api"].detail


def test_claude_health_uses_current_model_metadata(monkeypatch):
    from src.monitoring.health.dimensions.llm import LLMChecker
    from src.monitoring.health.report import CheckStatus

    seen = []
    monkeypatch.setattr("anthropic.Anthropic", lambda **kwargs:
                        SimpleNamespace(models=SimpleNamespace(retrieve=seen.append)))
    settings = SimpleNamespace(llm=SimpleNamespace(provider="claude", model=None),
                               anthropic_api_key="test")
    result = LLMChecker(settings)._check_claude_api()
    assert seen == ["claude-sonnet-5-5"] and result.status == CheckStatus.OK


def test_config_health_requires_separate_openai_agent_credentials():
    from src.monitoring.health.dimensions.config_env import ConfigEnvChecker
    from src.monitoring.health.report import CheckStatus

    settings = SimpleNamespace(
        llm=SimpleNamespace(provider="claude_code"),
        agent=AgentConfig(provider="openai", model="gpt-6-astra", research_model="gpt-6-astra"),
        alpaca_api_key="test", alpaca_api_secret="test", openai_api_key="", signals={},
        broker=SimpleNamespace(provider="alpaca"),
    )
    result = ConfigEnvChecker(settings)._check_env_vars()
    assert result.status == CheckStatus.ERROR and "OPENAI_API_KEY" in result.detail
