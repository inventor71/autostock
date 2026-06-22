"""U1 — AstScreen static pre-screen (defense-in-depth, not the boundary)."""

from __future__ import annotations

from src.agent.triggers.ast_screen import AstScreen

GOOD = """
import math
import json

def should_fire(ctx):
    vix = ctx.get("macro", {}).get("vix", 0)
    spy = ctx.get("macro", {}).get("spy_5d_ret", 0.0)
    fire = vix > 25 and spy < -0.04
    return {"fire": bool(fire), "why": f"vix={vix} spy5d={spy}"}
"""


def _codes(src: str) -> set[str]:
    return {v.code for v in AstScreen().check(src)}


def test_good_predicate_passes():
    assert AstScreen().check(GOOD) == []


def test_missing_entrypoint_rejected():
    assert "no-entrypoint" in _codes("import math\nx = 1\n")


def test_banned_import_os():
    src = "import os\ndef should_fire(ctx):\n    return {'fire': False}\n"
    assert "banned-import" in _codes(src)


def test_banned_import_subprocess_and_socket():
    for mod in ("subprocess", "socket", "sys", "importlib", "ctypes", "pathlib"):
        src = f"import {mod}\ndef should_fire(ctx):\n    return {{'fire': False}}\n"
        assert "banned-import" in _codes(src), mod


def test_banned_from_import():
    src = "from os import system\ndef should_fire(ctx):\n    return {'fire': False}\n"
    assert "banned-import" in _codes(src)


def test_relative_import_rejected():
    src = "from . import x\ndef should_fire(ctx):\n    return {'fire': False}\n"
    assert "relative-import" in _codes(src)


def test_banned_builtins():
    for name in ("eval", "exec", "open", "compile", "__import__", "getattr"):
        src = f"def should_fire(ctx):\n    {name}\n    return {{'fire': False}}\n"
        assert "banned-name" in _codes(src), name


def test_dunder_access_blocked():
    src = (
        "def should_fire(ctx):\n"
        "    return {'fire': bool(().__class__.__bases__)}\n"
    )
    assert "dunder-access" in _codes(src)


def test_async_entrypoint_rejected():
    src = "async def should_fire(ctx):\n    return {'fire': False}\n"
    assert "async-entrypoint" in _codes(src)


def test_syntax_error_reported():
    assert "syntax-error" in _codes("def should_fire(ctx)\n    return 1\n")


def test_allowed_imports_pass():
    for mod in ("statistics", "datetime", "re", "decimal", "itertools", "collections"):
        src = f"import {mod}\ndef should_fire(ctx):\n    return {{'fire': False}}\n"
        assert AstScreen().check(src) == [], mod
