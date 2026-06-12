"""Property-based + example tests for KIS price/qty normalization (F30, PBT Partial)."""

from __future__ import annotations

import math

from hypothesis import given, strategies as st

from src.execution.brokers.kis.pricing import floor_qty, round_to_tick, tick_size

# A realistic KRX price range (1 won .. 1,000,000 won).
prices = st.floats(min_value=1.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)


def test_tick_table_boundaries():
    # "이상~미만": the boundary value takes the upper band's tick.
    assert tick_size(1_999) == 1
    assert tick_size(2_000) == 5
    assert tick_size(4_999) == 5
    assert tick_size(5_000) == 10
    assert tick_size(49_999) == 50
    assert tick_size(50_000) == 100
    assert tick_size(199_999) == 100
    assert tick_size(200_000) == 500
    assert tick_size(499_999) == 500
    assert tick_size(500_000) == 1_000
    assert tick_size(1_000_000) == 1_000


def test_round_examples_including_boundary_crossing():
    assert round_to_tick(4_998) == 5_000  # crosses 2k–5k tier into 5k–20k
    assert round_to_tick(10_007) == 10_010
    assert round_to_tick(199_960) == 200_000  # crosses into 200k–500k tier
    assert round_to_tick(73_240) == 73_200


@given(prices)
def test_round_is_idempotent(p):
    r = round_to_tick(p)
    assert round_to_tick(r) == r  # fixed point


@given(prices)
def test_round_is_multiple_of_output_tier_tick(p):
    r = round_to_tick(p)
    assert r % tick_size(r) == 0  # multiple of its OWN tier's tick


@given(prices)
def test_round_within_one_tick(p):
    r = round_to_tick(p)
    # nearest rounding stays within one (input) tick of the price
    assert abs(r - p) <= tick_size(p)


@given(st.lists(prices, min_size=2, max_size=50))
def test_round_is_monotonic(ps):
    ps_sorted = sorted(ps)
    rounded = [round_to_tick(x) for x in ps_sorted]
    assert rounded == sorted(rounded)  # non-decreasing


@given(st.floats(min_value=0.0, max_value=1e6, allow_nan=False))
def test_floor_qty_invariants(q):
    n = floor_qty(q)
    assert isinstance(n, int)
    assert n <= q
    assert q - n < 1.0
    assert n == math.floor(q)
