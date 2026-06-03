"""KIS Korean-equity price/quantity normalization helpers (pure functions).

KIS domestic orders are integer-priced on the KRX tick grid and integer-sized
(no fractional shares). These helpers are broker-agnostic and pure so they can be
property-tested without any network/SDK.

Tick table: the 2023 KRX unification (KOSPI == KOSDAQ), "이상~미만" bands.
"""

from __future__ import annotations

import math

# (upper_exclusive_bound, tick). A price ``p`` uses the first tick whose bound > p.
_TICK_TABLE: list[tuple[float, int]] = [
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
]
_TOP_TICK = 1_000  # >= 500,000


def tick_size(price: float) -> int:
    """KRX tick for ``price`` (band by "이상~미만"). Boundaries take the upper band
    (e.g. exactly 2,000 -> 5-won tick)."""
    for bound, tick in _TICK_TABLE:
        if price < bound:
            return tick
    return _TOP_TICK


def round_to_tick(price: float) -> int:
    """Snap ``price`` to the nearest valid KRX tick.

    The band is chosen from the input, but nearest-rounding can push the result
    across a band boundary into a coarser tier; we re-snap to the *output* tier
    so the result is always a multiple of its own tier's tick (a fixed point).
    Every band boundary is itself a multiple of the higher tier's tick, so one
    re-snap suffices.
    """
    if price <= 0:
        return 0
    snapped = float(price)
    for _ in range(4):  # iterate to a true fixed point; converges in ≤2 for the table
        tick = tick_size(snapped)
        nxt = round(snapped / tick) * tick
        if nxt == snapped:
            break
        snapped = nxt
    return int(snapped)


def floor_qty(qty: float) -> int:
    """Floor a (possibly fractional) quantity to whole shares (KIS has no
    fractional shares). Callers reject the order when the result is < 1."""
    return int(math.floor(qty))
