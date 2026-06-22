"""F90: per-instance settings env overrides (Docker prod multi-instance)."""

from __future__ import annotations

import pytest

from config import config as cfg


def test_apply_env_overrides_injects_when_set(monkeypatch):
    monkeypatch.setenv("AUTOSTOCK_AGGRESSIVENESS", "aggressive")
    monkeypatch.setenv("AUTOSTOCK_BROKER_PROVIDER", "account_farm")
    c: dict = {"agent": {"model": "sonnet"}}
    cfg._apply_env_overrides(c)
    assert c["agent"]["aggressiveness"] == "aggressive"
    assert c["broker"]["provider"] == "account_farm"  # section created on demand


def test_apply_env_overrides_noop_when_unset(monkeypatch):
    monkeypatch.delenv("AUTOSTOCK_AGGRESSIVENESS", raising=False)
    monkeypatch.delenv("AUTOSTOCK_BROKER_PROVIDER", raising=False)
    c: dict = {"agent": {"aggressiveness": "balanced"}}
    cfg._apply_env_overrides(c)
    assert c["agent"]["aggressiveness"] == "balanced"  # YAML value stands
    assert "broker" not in c


def test_get_settings_applies_override(monkeypatch):
    monkeypatch.setenv("AUTOSTOCK_AGGRESSIVENESS", "aggressive")
    cfg.get_settings.cache_clear()
    try:
        s = cfg.get_settings()
        assert s.agent.aggressiveness == "aggressive"
    finally:
        cfg.get_settings.cache_clear()


def test_get_settings_override_runs_f85_failsafe(monkeypatch):
    """An invalid override coerces to balanced via the F85 field validator —
    not a crash (a typo in a container env must not wedge the daemon)."""
    monkeypatch.setenv("AUTOSTOCK_AGGRESSIVENESS", "agressive")  # typo
    cfg.get_settings.cache_clear()
    try:
        assert cfg.get_settings().agent.aggressiveness == "balanced"
    finally:
        cfg.get_settings.cache_clear()


def test_get_settings_default_unchanged(monkeypatch):
    monkeypatch.delenv("AUTOSTOCK_AGGRESSIVENESS", raising=False)
    monkeypatch.delenv("AUTOSTOCK_BROKER_PROVIDER", raising=False)
    cfg.get_settings.cache_clear()
    try:
        s = cfg.get_settings()
        assert s.agent.aggressiveness == "balanced"  # shipped settings.yaml default
    finally:
        cfg.get_settings.cache_clear()
