"""Unit A steering-core -- Step 8: PreToolUse deny-hook logic + token scrub (BR-10)."""

from __future__ import annotations

import json

from src.agent.steering.security import (
    TOKEN_ENV_VAR,
    evaluate,
    path_is_inside,
    scrub_agent_env,
    write_agent_hook_settings,
)


def test_path_inside_and_outside(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "sub").mkdir(parents=True)
    (ws / "sub" / "f.txt").write_text("x")
    outside = tmp_path / "secret.txt"
    outside.write_text("s")
    assert path_is_inside(str(ws / "sub" / "f.txt"), str(ws)) is True
    assert path_is_inside(str(outside), str(ws)) is False
    assert path_is_inside(str(ws), str(ws)) is True  # root itself


def test_evaluate_allows_inside_denies_outside(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    inside = str(ws / "journal.jsonl")
    outside = str(tmp_path / "steering" / "commands.jsonl")

    ok, _ = evaluate("Read", {"file_path": inside}, str(ws))
    assert ok is True
    ok, reason = evaluate("Write", {"file_path": outside}, str(ws))
    assert ok is False and "outside the agent workspace" in reason
    # a tool call with no path arg (e.g. workspace-relative Glob) is allowed
    assert evaluate("Glob", {"pattern": "*.md"}, str(ws)) == (True, "")


def test_evaluate_checks_notebook_and_search_path(tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    assert evaluate("NotebookEdit", {"notebook_path": str(tmp_path / "x.ipynb")}, str(ws))[0] is False
    assert evaluate("Grep", {"path": str(tmp_path / "elsewhere")}, str(ws))[0] is False


def test_scrub_agent_env_removes_token():
    env = {"PATH": "/usr/bin", TOKEN_ENV_VAR: "supersecret"}
    scrubbed = scrub_agent_env(env)
    assert TOKEN_ENV_VAR not in scrubbed
    assert scrubbed["PATH"] == "/usr/bin"  # other vars preserved


def test_write_agent_hook_settings(tmp_path):
    p = write_agent_hook_settings(tmp_path / "ws")
    data = json.loads(p.read_text())
    hook = data["hooks"]["PreToolUse"][0]
    assert "Read" in hook["matcher"] and "Write" in hook["matcher"]
    assert hook["hooks"][0]["command"].startswith("python3 ")
    assert hook["hooks"][0]["command"].endswith("security.py")
