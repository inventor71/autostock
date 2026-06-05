"""Mover detection — pure (F61, FR-1 / business-rule R1).

A scan row qualifies as a mover when its absolute price change clears
``price_pct`` OR its volume ratio clears ``vol_ratio`` (``require="both"`` makes
it AND). Output is sorted by ``abs(change_pct)`` descending and capped.
"""

from __future__ import annotations

import math
from typing import Literal

from src.signals.records import Mover, MoverRow


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


def _is_nan(value) -> bool:
    return isinstance(value, float) and math.isnan(value)


def detect_movers(
    rows: list[MoverRow],
    *,
    price_pct: float,
    vol_ratio: float,
    universe: set[str],
    require: Literal["any", "both"] = "any",
    max_movers: int = 12,
) -> list[Mover]:
    """Return the rows that cleared the mover threshold.

    Pure: same inputs → same output. ``universe`` (normalized) decides each
    mover's ``in_universe`` flag — a bellwether-only trigger is still a mover.
    """
    uni = {_norm(s) for s in universe}
    movers: list[Mover] = []

    for row in rows:
        # A missing OR NaN change is unusable — data providers (yfinance) can
        # return NaN for halted/stale/just-listed bars. Without a real change we
        # can't report magnitude/direction or a read-through trigger, so skip the
        # row entirely rather than emit a "+nan%" mover.
        if row.change_pct is None or _is_nan(row.change_pct):
            continue
        chg = row.change_pct
        vr = None if _is_nan(row.volume_ratio) else row.volume_ratio

        qualified_by: list[Literal["price", "volume"]] = []
        if abs(chg) >= price_pct:
            qualified_by.append("price")
        if vr is not None and vr >= vol_ratio:
            qualified_by.append("volume")

        if require == "both":
            ok = "price" in qualified_by and "volume" in qualified_by
        else:
            ok = bool(qualified_by)
        if not ok:
            continue

        sym = _norm(row.symbol)
        movers.append(
            Mover(
                symbol=sym,
                change_pct=chg,
                volume_ratio=vr,
                close=row.close,
                direction="up" if chg >= 0 else "down",
                in_universe=sym in uni,
                qualified_by=qualified_by,
            )
        )

    # Strongest moves first; stable secondary sort by symbol for determinism.
    movers.sort(key=lambda m: (-abs(m.change_pct), m.symbol))
    return movers[:max_movers]
