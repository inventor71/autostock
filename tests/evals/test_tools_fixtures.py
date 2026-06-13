"""Fixture/record interception for the agent tool CLI (F74 U1).

The eval harness depends on two hard guarantees:
- a market command in fixture mode is answered from the scenario fixture and
  NEVER reaches the live data wiring (no silent fallback), and
- record mode captures real outputs in exactly the format fixture mode reads
  back (round-trip), so captured sessions become scenarios verbatim.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings

from src.agent.tools import __main__ as tools_main
from src.agent.tools.fixtures import (
    FIXTURE_ENV,
    MARKET_COMMANDS,
    NO_SYMBOL_KEY,
    RECORD_ENV,
    FixtureStore,
    RecordingStore,
)
from tests.evals import generators as gen


def _run_cli(capsys, argv: list[str]) -> dict | list:
    assert tools_main.main(argv) == 0
    return json.loads(capsys.readouterr().out)


class TestFixtureStore:
    def test_missing_file_is_explicit_error(self, tmp_path):
        out = FixtureStore(tmp_path).get("quote", "AAPL")
        assert out["error"] == "fixture_missing"
        assert out["tool"] == "quote" and out["key"] == "AAPL"

    def test_missing_key_is_explicit_error(self, tmp_path):
        (tmp_path / "quote.json").write_text(json.dumps({"MSFT": {"price": 1}}))
        out = FixtureStore(tmp_path).get("quote", "AAPL")
        assert out["error"] == "fixture_missing"

    def test_unreadable_file_is_explicit_error(self, tmp_path):
        (tmp_path / "quote.json").write_text("{not json")
        out = FixtureStore(tmp_path).get("quote", "AAPL")
        assert out["error"] == "fixture_unreadable"

    @settings(max_examples=50)
    @given(cmd=gen.market_commands, key=gen.fixture_keys, output=gen.tool_outputs)
    def test_record_fixture_round_trip(self, tmp_path_factory, cmd, key, output):
        """INV-1 (PBT-02): save -> get returns the stored output exactly."""
        root = tmp_path_factory.mktemp("fx")
        RecordingStore(root).save(cmd, key, output)
        got = FixtureStore(root).get(cmd, key)
        # default=str in save may stringify exotic values; our generator emits
        # plain JSON values, so equality must hold exactly.
        assert got == json.loads(json.dumps(output))

    @settings(max_examples=50)
    @given(cmd=gen.market_commands, key=gen.fixture_keys, output=gen.tool_outputs,
           other_key=gen.fixture_keys)
    def test_no_silent_substitute(self, tmp_path_factory, cmd, key, output, other_key):
        """INV-2 (PBT-03): get returns the stored object or fixture_missing —
        never another key's value."""
        root = tmp_path_factory.mktemp("fx")
        RecordingStore(root).save(cmd, key, output)
        got = FixtureStore(root).get(cmd, other_key)
        if other_key == key:
            assert got == json.loads(json.dumps(output))
        else:
            assert isinstance(got, dict) and got.get("error") == "fixture_missing"

    def test_save_merges_keys(self, tmp_path):
        rec = RecordingStore(tmp_path)
        rec.save("quote", "AAPL", {"price": 1})
        rec.save("quote", "MSFT", {"price": 2})
        store = FixtureStore(tmp_path)
        assert store.get("quote", "AAPL") == {"price": 1}
        assert store.get("quote", "MSFT") == {"price": 2}


class TestDispatchInterception:
    def test_fixture_mode_serves_market_command(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "quote.json").write_text(json.dumps({"AAPL": {"price": 123.45}}))
        monkeypatch.setenv(FIXTURE_ENV, str(tmp_path))
        # INV-3: live wiring must not be touched — make it explosive.
        monkeypatch.setattr(tools_main, "_provider",
                            lambda: pytest.fail("live provider built in fixture mode"))
        out = _run_cli(capsys, ["quote", "AAPL"])
        assert out == {"price": 123.45}

    def test_fixture_mode_symbol_less_command(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "account.json").write_text(
            json.dumps({NO_SYMBOL_KEY: {"equity": 100000.0}}))
        monkeypatch.setenv(FIXTURE_ENV, str(tmp_path))
        monkeypatch.setattr(tools_main, "_broker",
                            lambda: pytest.fail("live broker built in fixture mode"))
        out = _run_cli(capsys, ["account"])
        assert out == {"equity": 100000.0}

    def test_fixture_mode_missing_key_fail_honest(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv(FIXTURE_ENV, str(tmp_path))
        out = _run_cli(capsys, ["quote", "NVDA"])
        assert out["error"] == "fixture_missing"

    def test_fixture_mode_symbol_key_uppercased(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "quote.json").write_text(json.dumps({"AAPL": {"price": 1}}))
        monkeypatch.setenv(FIXTURE_ENV, str(tmp_path))
        assert _run_cli(capsys, ["quote", "aapl"]) == {"price": 1}

    def test_workspace_command_passes_through(self, tmp_path, capsys, monkeypatch):
        """lesson/watch/surge are not market data: they must keep operating on
        the (sandbox) journal even in fixture mode."""
        monkeypatch.setenv(FIXTURE_ENV, str(tmp_path))
        ws = tmp_path / "ws"
        monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(ws))
        out = _run_cli(capsys, [
            "lesson", "add", "--takeaway", "test lesson", "--regime", "risk-on",
        ])
        assert out["added"]["takeaway"] == "test lesson"
        assert (ws / "lessons.jsonl").exists()

    def test_no_env_uses_live_wiring(self, capsys, monkeypatch):
        """Behavior preservation: without the env vars the dispatch calls the
        real market function with the real provider factory."""
        monkeypatch.delenv(FIXTURE_ENV, raising=False)
        monkeypatch.delenv(RECORD_ENV, raising=False)
        calls = {}

        def fake_quote(sym, prov):
            calls["args"] = (sym, prov)
            return {"ok": 1}

        monkeypatch.setattr(tools_main, "_provider", lambda: "prov")
        monkeypatch.setattr(tools_main.market, "quote", fake_quote)
        assert _run_cli(capsys, ["quote", "AAPL"]) == {"ok": 1}
        assert calls["args"] == ("AAPL", "prov")

    def test_record_mode_captures_output(self, tmp_path, capsys, monkeypatch):
        monkeypatch.delenv(FIXTURE_ENV, raising=False)
        monkeypatch.setenv(RECORD_ENV, str(tmp_path))
        monkeypatch.setattr(tools_main, "_provider", lambda: None)
        monkeypatch.setattr(tools_main.market, "quote", lambda sym, prov: {"price": 9.9})
        _run_cli(capsys, ["quote", "TSLA"])
        assert FixtureStore(tmp_path).get("quote", "TSLA") == {"price": 9.9}

    def test_fixture_wins_over_record(self, tmp_path, capsys, monkeypatch):
        fx = tmp_path / "fx"
        fx.mkdir()
        (fx / "quote.json").write_text(json.dumps({"AAPL": {"price": 1}}))
        rec = tmp_path / "rec"
        monkeypatch.setenv(FIXTURE_ENV, str(fx))
        monkeypatch.setenv(RECORD_ENV, str(rec))
        assert _run_cli(capsys, ["quote", "AAPL"]) == {"price": 1}
        assert not (rec / "quote.json").exists()

    def test_all_market_commands_intercepted(self, tmp_path, capsys, monkeypatch):
        """Every market command answers from fixture (fail-honest when absent)
        without touching any live factory."""
        monkeypatch.setenv(FIXTURE_ENV, str(tmp_path))
        for fac in ("_provider", "_broker", "_signal_collector", "_universe"):
            monkeypatch.setattr(
                tools_main, fac,
                lambda *a, fac=fac, **k: pytest.fail(f"{fac} built in fixture mode"))
        argv_by_cmd = {
            "macro": ["macro"], "account": ["account"], "movers": ["movers"],
            "scoreboard": ["scoreboard"], "earnings_calendar": ["earnings_calendar"],
        }
        for cmd in sorted(MARKET_COMMANDS):
            argv = argv_by_cmd.get(cmd, [cmd, "AAPL"])
            out = _run_cli(capsys, argv)
            assert out.get("error") == "fixture_missing", cmd
