"""Tier-1 multi-scenario corpus (F61, deterministic, zero-token).

Each fixture in ``scenarios/*.json`` carries inputs + expected output. The corpus
covers both true-positives (read-through fires when it should — S1/S2/S3) and
false-positive guards (it stays silent when it should — S4/S5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.signals.conftest import build_scenario_brief

_SCENARIO_DIR = Path(__file__).parent / "scenarios"
_SCENARIOS = sorted(_SCENARIO_DIR.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _SCENARIOS, ids=[p.stem for p in _SCENARIOS])
def test_scenario(path: Path):
    scenario = _load(path)
    expect = scenario["expect"]
    brief = build_scenario_brief(scenario)

    mover_syms = {m.symbol for m in brief.movers}
    assert mover_syms == set(expect["mover_symbols"]), f"movers mismatch in {path.stem}"

    # out-of-universe movers are flagged (bellwether triggers)
    for sym in expect.get("mover_out_of_universe", []):
        m = next(m for m in brief.movers if m.symbol == sym)
        assert m.in_universe is False

    trigger_syms = {a.trigger_symbol for a in brief.readthrough_alerts}
    assert trigger_syms == set(expect["readthrough_triggers"]), \
        f"readthrough triggers mismatch in {path.stem}"

    if expect.get("no_readthrough"):
        assert brief.readthrough_alerts == []

    if expect.get("empty_brief"):
        assert brief.is_empty()

    by_trigger = {a.trigger_symbol: a for a in brief.readthrough_alerts}
    for trig, peers in expect.get("readthrough_peers_include", {}).items():
        got = set(by_trigger[trig].affected_peers)
        assert set(peers) <= got, f"{trig}: expected peers {peers} ⊆ {got}"
    for trig, peers in expect.get("readthrough_peers_exclude", {}).items():
        got = set(by_trigger[trig].affected_peers)
        assert not (set(peers) & got), f"{trig}: peers {peers} should be absent from {got}"

    for trig, frag in expect.get("cause_hint_contains", {}).items():
        hint = by_trigger[trig].cause_hint or ""
        assert frag.lower() in hint.lower()


def test_corpus_has_true_and_false_positive_cases():
    """The corpus must exercise both directions (else it proves nothing)."""
    types = {_load(p).get("type", "") for p in _SCENARIOS}
    assert "earnings_shock_readthrough" in types  # true positive
    assert "idiosyncratic_no_readthrough" in types  # false-positive guard
    assert "quiet_day" in types  # silence guard
