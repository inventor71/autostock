"""Scenario schema: serialization round-trip (PBT-02) + validation rules."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from src.evals.scenario import Expectation, Scenario, load_scenario, save_scenario
from tests.evals import generators as gen

expectations = st.builds(
    Expectation,
    no_churn=st.booleans(),
    allowed_actions=st.lists(gen.actions, max_size=3, unique=True),
    focus_symbol=st.one_of(st.none(), gen.symbols),
    note=st.text(max_size=30),
)

scenarios = st.builds(
    Scenario,
    id=st.from_regex(r"[a-z0-9-]{1,24}", fullmatch=True),
    turn_type=st.sampled_from(["intraday", "wake", "eod"]),
    origin=st.text(max_size=30),
    universe=st.lists(gen.symbols, min_size=1, max_size=5, unique=True),
    brief=st.one_of(st.none(), st.text(max_size=120)),
    wake_reasons=st.lists(st.text(min_size=1, max_size=40), max_size=3),
    tool_fixtures=st.dictionaries(
        gen.market_commands,
        st.dictionaries(gen.fixture_keys, gen.tool_outputs, max_size=2),
        max_size=3,
    ),
    workspace_files=st.dictionaries(
        st.sampled_from(["lessons.md", "regime.md", "positions/AAPL.md"]),
        st.text(max_size=80),
        max_size=3,
    ),
    held=st.dictionaries(
        gen.symbols,
        st.fixed_dictionaries({
            "qty": st.integers(min_value=1, max_value=500),
            "avg_entry_price": st.floats(min_value=1, max_value=1000,
                                         allow_nan=False, width=32),
            "side": gen.sides,
        }),
        max_size=2,
    ),
    prices=st.dictionaries(gen.symbols,
                           st.floats(min_value=1, max_value=10000,
                                     allow_nan=False, width=32),
                           max_size=3),
    expectation=expectations,
)


class TestScenarioSchema:
    @settings(max_examples=40)
    @given(scenario=scenarios)
    def test_file_round_trip(self, tmp_path_factory, scenario):
        """PBT-02: save -> load reproduces the scenario exactly."""
        path = tmp_path_factory.mktemp("sc") / "s.json"
        save_scenario(scenario, path)
        assert load_scenario(path) == scenario

    def test_unknown_action_rejected(self):
        with pytest.raises(ValidationError):
            Expectation(allowed_actions=["CLOSE"])  # not a journal action

    def test_empty_universe_rejected(self):
        with pytest.raises(ValidationError):
            Scenario(id="x", turn_type="intraday", universe=[],
                     expectation=Expectation(no_churn=True))

    def test_symbols_uppercased(self):
        s = Scenario(id="x", turn_type="intraday", universe=["aapl"],
                     expectation=Expectation(focus_symbol="aapl", no_churn=True))
        assert s.universe == ["AAPL"]
        assert s.expectation.focus_symbol == "AAPL"
