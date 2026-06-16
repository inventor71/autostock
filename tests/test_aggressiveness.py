"""F85: aggressiveness knob — preset SSOT, config fail-safe, risk overlay,
prompt fan-out, decision stamping, and the learning-loop maturity/normalization."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from hypothesis import given, strategies as st

from src.agent import prompts
from src.agent.aggressiveness import (
    ALLOWED_RISK_KEYS,
    PROFILES,
    AggressivenessProfile,
    resolve,
)
from src.agent.journal import Decision
from src.agent.learning.efficacy import lesson_efficacy, prompt_version_efficacy
from src.agent.quality.models import DecisionOutcome


# ── SSOT preset module ──────────────────────────────────────────────────────

def test_three_levels_present():
    assert set(PROFILES) == {"conservative", "balanced", "aggressive"}


def test_balanced_is_identity():
    """balanced overlays nothing and injects nothing → pre-F85 behavior exactly."""
    b = resolve("balanced")
    assert b.risk_overlay == {}
    assert b.disposition == ""
    assert b.intraday_churn == ""
    assert b.short_tilt == ""


@pytest.mark.parametrize("bad", ["aggresive", "AGGRESSIVE_", "", "x", None])
def test_resolve_fail_safe(bad):
    """Unknown/None falls back to balanced (mirrors the config validator)."""
    assert resolve(bad).level == "balanced"


@pytest.mark.parametrize("level", ["conservative", "balanced", "aggressive"])
def test_resolve_case_insensitive(level):
    assert resolve(level.upper()).level == level


def test_overlay_keys_are_allowlisted():
    """No profile may overlay a non-allowlisted key (e.g. a safety gate)."""
    for p in PROFILES.values():
        assert set(p.risk_overlay) <= ALLOWED_RISK_KEYS


def test_profile_rejects_non_allowlisted_overlay():
    with pytest.raises(ValueError):
        AggressivenessProfile(
            level="x", risk_overlay={"shorting_enabled": True},
            disposition="", intraday_churn="", short_tilt="",
            grading_horizon_days=10, recall_recency=0.5,
        )


def test_monotonicity_across_levels():
    """Example-based (PROFILES is a fixed 3-entry table, not a generated domain):
    risk appetite rises and grading horizon shortens conservative→aggressive."""
    c, b, a = resolve("conservative"), resolve("balanced"), resolve("aggressive")
    assert c.risk_overlay["max_position_pct"] < b.risk_overlay.get("max_position_pct", 0.05) < a.risk_overlay["max_position_pct"]
    assert c.grading_horizon_days > b.grading_horizon_days > a.grading_horizon_days
    assert c.recall_recency < b.recall_recency < a.recall_recency


@given(st.text())
def test_resolve_property_arbitrary_string(s):
    """Any string that isn't a known level resolves to balanced; never raises."""
    p = resolve(s)
    assert p.level in {"conservative", "balanced", "aggressive"}
    if s.lower() not in PROFILES:
        assert p.level == "balanced"


# ── config validator fail-safe ──────────────────────────────────────────────

def test_config_validator_coerces_unknown_to_balanced():
    from config.config import AgentConfig

    assert AgentConfig(aggressiveness="aggressive").aggressiveness == "aggressive"
    assert AgentConfig(aggressiveness="AGGRESSIVE").aggressiveness == "aggressive"
    assert AgentConfig(aggressiveness="nonsense").aggressiveness == "balanced"
    assert AgentConfig().aggressiveness == "balanced"  # default


# ── Decision stamping round-trip ────────────────────────────────────────────

def test_decision_new_fields_roundtrip_and_legacy_default():
    d = Decision(symbol="nvda", action="BUY", aggressiveness="aggressive",
                 grading_horizon_days=3)
    again = Decision.model_validate_json(d.model_dump_json())
    assert again.aggressiveness == "aggressive" and again.grading_horizon_days == 3
    # A legacy line lacking the fields parses with the shipped 'balanced' defaults.
    legacy = Decision.model_validate_json('{"symbol": "AAPL", "action": "BUY"}')
    assert legacy.aggressiveness == "balanced" and legacy.grading_horizon_days == 20


# ── risk overlay (FR-3/FR-6, use_bracket_orders per-site) ───────────────────

class _Settings:
    def __init__(self, level):
        from config.config import AgentConfig, RiskConfig
        self.risk = RiskConfig(shorting_enabled=True)  # gate ON to prove it survives
        self.agent = AgentConfig(aggressiveness=level)


@pytest.mark.parametrize("level", ["conservative", "balanced", "aggressive"])
def test_risk_overlay_preserves_short_gate_and_bracket(level):
    from main import _build_risk_manager

    rm = _build_risk_manager(_Settings(level), use_bracket_orders=True,
                             apply_aggressiveness=True)
    # FR-6: the short master toggle is never touched by the overlay.
    assert rm.shorting_enabled is True
    # use_bracket_orders is a per-site kwarg, never dropped by the overlay.
    assert rm.use_bracket_orders is True
    # The overlaid sizing matches the profile (balanced == shipped default).
    expected = resolve(level).risk_overlay.get("max_position_pct", _Settings(level).risk.max_position_pct)
    assert rm.position_sizer.max_position_pct == expected


def test_overlay_off_leaves_settings_untouched():
    from main import _build_risk_manager

    s = _Settings("aggressive")
    rm = _build_risk_manager(s, use_bracket_orders=False)  # apply_aggressiveness default False
    assert rm.position_sizer.max_position_pct == s.risk.max_position_pct


# ── prompt fan-out (delta injection; balanced empty == unchanged) ───────────

def test_balanced_prompt_byte_identical():
    base = prompts.morning_research_prompt(["AAPL"], disposition="")
    assert base == prompts.morning_research_prompt(["AAPL"])  # no posture arg


def test_disposition_injected_into_builders():
    disp = resolve("aggressive").disposition
    for text in (
        prompts.morning_research_prompt(["AAPL"], disposition=disp),
        prompts.synthesis_prompt(2, disposition=disp),
        prompts.sub_agent_prompt("task", ["AAPL"], disposition=disp),
        prompts.parallel_synthesis_prompt(["r"], disposition=disp),
        prompts.wake_prompt(None, ["fill"], disposition=disp),
        prompts.intraday_prompt(brief="b", disposition=disp),
    ):
        assert "Posture — aggressive" in text


def test_intraday_churn_override():
    out = prompts.intraday_prompt(brief="b", churn=resolve("aggressive").intraday_churn)
    assert "Act on intraday triggers" in out and "do not churn" not in out
    # balanced keeps the shipped guidance
    assert "do not churn" in prompts.intraday_prompt(brief="b")


# ── learning: maturity gate + per-day normalization ─────────────────────────

def _outcome(*, excess, mature, holding_days=1, version="v1", lessons=("L1",)):
    d = Decision(symbol="AAPL", action="BUY", prompt_version=version,
                 lessons_cited=list(lessons))
    return DecisionOutcome(decision=d, excess=excess, mature=mature,
                           holding_days=holding_days)


def test_immature_excluded_from_efficacy():
    outs = [_outcome(excess=0.1, mature=False), _outcome(excess=0.2, mature=True)]
    le = lesson_efficacy(outs)
    ve = prompt_version_efficacy(outs)
    assert le["L1"].applied_n == 1  # only the mature one
    assert ve["v1"].applied_n == 1


def test_per_day_normalization_makes_horizons_comparable():
    # A 45-day hold with +9% excess and a 3-day hold with +0.6% excess both
    # normalize to ~+0.2%/day — neither dominates the bucket mean.
    outs = [
        _outcome(excess=0.09, mature=True, holding_days=45),
        _outcome(excess=0.006, mature=True, holding_days=3),
    ]
    ve = prompt_version_efficacy(outs)["v1"]
    assert ve.applied_n == 2
    assert ve.avg_excess == pytest.approx((0.09 / 45 + 0.006 / 3) / 2)
    assert ve.win_rate == 1.0  # sign preserved


@given(
    age=st.integers(min_value=0, max_value=120),
    horizon=st.integers(min_value=1, max_value=90),
)
def test_maturity_boundary_property(age, horizon):
    """A decision is mature iff its horizon has elapsed (age >= horizon)."""
    ts = datetime.now() - timedelta(days=age)
    mature = (datetime.now().date() - ts.date()).days >= horizon
    assert mature == (age >= horizon)


# ── grade_matured ledger (idempotent, EOD-only writer) ──────────────────────

def test_grade_matured_idempotent_and_skips_immature(tmp_path):
    import json

    from src.agent.journal import Journal
    from src.agent.quality.collector import grade_matured

    journal = Journal(root=tmp_path)
    outs = [
        DecisionOutcome(decision=Decision(symbol="AAPL", action="BUY"),
                        excess=0.05, mature=True, holding_days=5, decision_index=0),
        DecisionOutcome(decision=Decision(symbol="MSFT", action="BUY"),
                        excess=0.02, mature=False, holding_days=1, decision_index=1),
    ]
    assert grade_matured(journal, outs) == 1  # only the mature one
    assert grade_matured(journal, outs) == 0  # second pass: idempotent, no re-append
    lines = (tmp_path / "grades.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["decision_index"] == 0 and rec["win"] is True
    assert rec["excess_per_day"] == pytest.approx(0.05 / 5)
