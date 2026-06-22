"""U5 — TriggersConfig + ctx-schema doc seeding."""

from __future__ import annotations

from src.agent.triggers.schema_doc import CTX_SCHEMA_MD, write_ctx_schema
from src.agent.triggers.settings import TriggersConfig


def test_config_defaults_off():
    cfg = TriggersConfig.from_settings(None)
    assert cfg.enabled is False
    assert cfg.tick_seconds >= 30
    assert cfg.sandbox_image.startswith("python@sha256:")  # digest pinned (SECURITY-10)
    assert cfg.webfetch_allowlist == []


def test_config_from_block():
    cfg = TriggersConfig.from_settings({
        "enabled": True, "tick_seconds": 600, "webfetch_allowlist": ["stlouisfed.org"],
        "max_consecutive_errors": 3,
    })
    assert cfg.enabled is True
    assert cfg.tick_seconds == 600
    assert cfg.webfetch_allowlist == ["stlouisfed.org"]
    assert cfg.max_consecutive_errors == 3


def test_schema_doc_contract_is_complete():
    # the agent's only channel to the predicate contract (critic#7)
    assert "should_fire(ctx)" in CTX_SCHEMA_MD
    assert "fire" in CTX_SCHEMA_MD and "why" in CTX_SCHEMA_MD
    assert "_error" in CTX_SCHEMA_MD            # documents fail-honest sources
    assert "trigger register" in CTX_SCHEMA_MD  # how to register


def test_write_ctx_schema(tmp_path):
    path = write_ctx_schema(tmp_path / "triggers")
    assert path.is_file()
    assert "should_fire" in path.read_text()
