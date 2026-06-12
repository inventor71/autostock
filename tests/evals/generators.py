"""Central hypothesis generators for the F74 eval-harness domain (PBT-07).

Shared by the fixture-store, scenario-schema, and grading property tests so
domain constraints live in one place instead of being re-invented per file.
"""

from __future__ import annotations

from hypothesis import strategies as st

from src.agent.tools.fixtures import MARKET_COMMANDS, NO_SYMBOL_KEY

# Plausible ticker symbols (incl. the boundary of 1-char and 5-char tickers).
symbols = st.from_regex(r"[A-Z]{1,5}", fullmatch=True)

fixture_keys = st.one_of(st.just(NO_SYMBOL_KEY), symbols)

market_commands = st.sampled_from(sorted(MARKET_COMMANDS))

# JSON-serializable tool outputs as the tools actually emit them: dicts (and
# occasionally lists, e.g. scoreboard) of scalars/nested containers.
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10**9, max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=40),
)
json_values = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(min_size=1, max_size=12), children, max_size=4),
    ),
    max_leaves=12,
)
tool_outputs = st.one_of(
    st.dictionaries(st.text(min_size=1, max_size=12), json_values, max_size=6),
    st.lists(st.dictionaries(st.text(min_size=1, max_size=12), json_values, max_size=4),
             max_size=4),
)

# Decision action vocabulary (mirrors src/agent/journal.py DecisionAction).
actions = st.sampled_from(["BUY", "SELL", "HOLD", "ADJUST_STOP", "SELL_SHORT", "BUY_TO_COVER"])
sides = st.sampled_from(["long", "short"])
