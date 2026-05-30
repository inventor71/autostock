"""Abnormal-move detection (FR-4-C, Q4=A): |move| > k*ATR OR volume > m*avg.

The threshold predicates are pure (PBT targets); ``detect_abnormal`` wires them
to cached bars/price. Thresholds come from ``config/settings.yaml`` (intraday
block) — defaults here are the fail-safe when the block is absent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.agent.intraday.bars import atr, avg_volume
from src.agent.intraday.records import AbnormalMoveSignal


@dataclass(frozen=True)
class AbnormalConfig:
    atr_k: float = 1.5
    vol_multiple: float = 3.0
    atr_period: int = 14


def breaches_atr(move: float, atr_value: float, k: float) -> bool:
    """|move| strictly exceeds k*ATR. Pure (PBT: monotonic in |move|, boundary)."""
    if atr_value <= 0 or k <= 0:
        return False
    return abs(move) > k * atr_value


def breaches_volume(volume: float, avg: float, m: float) -> bool:
    """volume strictly exceeds m*avg. Pure (PBT: monotonic in volume, boundary)."""
    if avg <= 0 or m <= 0:
        return False
    return volume > m * avg


def detect_abnormal(symbol: str, price: float | None, ref_price: float | None,
                    bars: pd.DataFrame | None, cfg: AbnormalConfig) -> AbnormalMoveSignal | None:
    """Return a signal if the intraday move or volume is abnormal, else None.

    ``ref_price`` is the comparison anchor (e.g. session open / previous close).
    Either condition firing is enough (Q4)."""
    if price is not None and ref_price is not None:
        a = atr(bars, cfg.atr_period)
        if a is not None and breaches_atr(price - ref_price, a, cfg.atr_k):
            move = abs(price - ref_price)
            return AbnormalMoveSignal(symbol=symbol, kind="price", magnitude=move,
                                      threshold=cfg.atr_k * a,
                                      reason=f"|move| {move:.2f} > {cfg.atr_k}*ATR {a:.2f}")
    av = avg_volume(bars)
    if bars is not None and len(bars) > 0 and av is not None:
        last_vol = float(bars["volume"].iloc[-1])
        if breaches_volume(last_vol, av, cfg.vol_multiple):
            return AbnormalMoveSignal(symbol=symbol, kind="volume", magnitude=last_vol,
                                      threshold=cfg.vol_multiple * av,
                                      reason=f"vol {last_vol:.0f} > {cfg.vol_multiple}*avg {av:.0f}")
    return None
