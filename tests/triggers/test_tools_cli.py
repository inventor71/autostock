"""U5 — `python -m src.agent.tools trigger ...` CLI (the agent's authoring surface).

The CLI writes to the SAME TriggerStore the daemon evaluator reads; tests drive it
through main() with AGENT_JOURNAL_ROOT pointed at a tmp workspace and parse the JSON
it prints to stdout.
"""

from __future__ import annotations

import json

import pytest

from src.agent.tools.__main__ import main

GOOD_PREDICATE = (
    "def should_fire(ctx):\n"
    "    return {'fire': ctx.get('macro', {}).get('vix', 0) > 25, 'why': 'vix'}\n"
)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    return tmp_path


def _run(capsys, *argv) -> dict:
    rc = main(list(argv))
    assert rc == 0
    return json.loads(capsys.readouterr().out)


def _pred_file(ws, src=GOOD_PREDICATE):
    p = ws / "pred.py"
    p.write_text(src)
    return str(p)


def test_register_success(ws, capsys):
    out = _run(
        capsys, "trigger", "register", "--id", "vix-spike", "--thesis", "VIX regime",
        "--cadence", "daily", "--ttl-days", "30",
        "--sources-json", '[{"kind":"signal","name":"macro"}]',
        "--predicate-file", _pred_file(ws),
    )
    assert out == {"ok": True, "id": "vix-spike"}
    assert (ws / "triggers" / "vix-spike" / "spec.json").is_file()


def test_register_screen_rejection_reports_violations(ws, capsys):
    bad = "import os\ndef should_fire(ctx):\n    return {'fire': False}\n"
    out = _run(
        capsys, "trigger", "register", "--id", "bad", "--thesis", "x",
        "--ttl-days", "5", "--predicate-file", _pred_file(ws, bad),
    )
    assert out["ok"] is False
    assert any("banned-import" in v for v in out["violations"])


def test_register_bad_sources_json_structured_error(ws, capsys):
    out = _run(
        capsys, "trigger", "register", "--id", "x", "--thesis", "t",
        "--ttl-days", "5", "--sources-json", '[{"kind":"signal"}]',  # missing name
        "--predicate-file", _pred_file(ws),
    )
    assert out["ok"] is False
    assert "error" in out


def test_list_and_inspect_and_cancel(ws, capsys):
    _run(capsys, "trigger", "register", "--id", "t1", "--thesis", "th1",
         "--ttl-days", "10", "--predicate-file", _pred_file(ws))

    listed = _run(capsys, "trigger", "list")
    assert [t["id"] for t in listed["triggers"]] == ["t1"]

    detail = _run(capsys, "trigger", "inspect", "t1")
    assert detail["spec"]["id"] == "t1"
    assert "should_fire" in detail["predicate_src"]
    assert detail["state"]["fired_count"] == 0

    cancelled = _run(capsys, "trigger", "cancel", "t1")
    assert cancelled == {"cancelled": True}
    assert _run(capsys, "trigger", "list")["triggers"] == []


def test_inspect_unknown_id(ws, capsys):
    out = _run(capsys, "trigger", "inspect", "ghost")
    assert out["ok"] is False


def test_no_entry_inducing_flag(ws, capsys):
    _run(capsys, "trigger", "register", "--id", "protect", "--thesis", "exit thesis",
         "--ttl-days", "10", "--no-entry-inducing", "--predicate-file", _pred_file(ws))
    detail = _run(capsys, "trigger", "inspect", "protect")
    assert detail["spec"]["entry_inducing"] is False
