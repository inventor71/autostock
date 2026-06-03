"""Pure-function signal detector for early-session moves.

Stateless — the sole method ``detect(bars)`` is a pure function suitable for
Hypothesis property-based testing (PBT-03).
"""

from __future__ import annotations

from datetime import date

from src.early_session.records import BarRecord, SignalEvent


class SignalDetector:
    """Detect ±threshold_pct% moves within *window_minutes*.

    Stateless. All parameters are injected at construction time.
    """

    def __init__(self, threshold_pct: float = 5.0, window_minutes: int = 10):
        self.threshold_pct = threshold_pct
        self.window_minutes = window_minutes

    def detect(self, bars: list[BarRecord]) -> SignalEvent | None:
        """Return a SignalEvent if the window triggers, or None.

        Pure function — no I/O, no global state.
        """
        if len(bars) < self.window_minutes:
            return None

        first_close = bars[0].close
        last_close = bars[-1].close
        if first_close == 0:
            return None

        change_pct = (last_close - first_close) / first_close * 100.0

        if abs(change_pct) < self.threshold_pct:
            return None

        direction = "surge" if change_pct > 0 else "drop"
        last = bars[-1]
        return SignalEvent(
            symbol=last.symbol,
            date=last.timestamp.date(),
            detected_at=last.timestamp,
            direction=direction,
            trigger_pct=round(change_pct, 2),
            trigger_window_min=self.window_minutes,
            open=0.0,  # filled by caller (monitor)
            prev_close=0.0,  # filled by caller
            gap_pct=0.0,  # filled by caller
        )
