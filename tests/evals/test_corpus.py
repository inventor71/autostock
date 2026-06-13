"""Committed scenario corpus: every file must be loadable, internally
consistent, and free of authoring leftovers. Token-zero."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.agent.tools.fixtures import MARKET_COMMANDS
from src.evals.scenario import load_scenario

EVALS = Path(__file__).resolve().parents[2] / "evals"
SCENARIOS = sorted((EVALS / "scenarios").rglob("*.json"))


def test_corpus_size_meets_v1_target():
    assert len(SCENARIOS) >= 10  # requirements acceptance: >= 10 scenarios


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
class TestEveryScenario:
    def test_loads_and_validates(self, path):
        load_scenario(path)

    def test_dir_matches_turn_type(self, path):
        assert load_scenario(path).turn_type == path.parent.name

    def test_fixture_commands_are_real_tools(self, path):
        s = load_scenario(path)
        unknown = set(s.tool_fixtures) - MARKET_COMMANDS
        assert not unknown, f"unknown tool fixtures: {unknown}"

    def test_no_manual_todos_left(self, path):
        assert "TODO_MANUAL" not in path.read_text(encoding="utf-8")

    def test_expectation_is_decidable(self, path):
        s = load_scenario(path)
        assert s.expectation.no_churn or s.expectation.allowed_actions

    def test_replay_prices_cover_universe_holdings(self, path):
        s = load_scenario(path)
        for sym in s.held:
            assert sym in s.prices, f"held {sym} has no replay price"

    def test_turn_inputs_present(self, path):
        s = load_scenario(path)
        if s.turn_type == "eod":
            assert s.eod_outcomes
        else:
            assert s.brief

    def test_origin_recorded(self, path):
        assert load_scenario(path).origin.strip()


def test_tests_yaml_rows_reference_existing_files():
    rows = yaml.safe_load((EVALS / "tests.yaml").read_text(encoding="utf-8"))
    assert len(rows) >= 11
    for row in rows:
        v = row["vars"]
        assert (EVALS / v["scenario"]).exists(), v["scenario"]
        if "guidance_file" in v:
            payload = json.loads((EVALS / v["guidance_file"]).read_text(encoding="utf-8"))
            assert payload["current_version"] in payload["versions"]


def test_corpus_covers_all_v1_turn_types():
    types = {load_scenario(p).turn_type for p in SCENARIOS}
    assert types == {"intraday", "wake", "eod"}
