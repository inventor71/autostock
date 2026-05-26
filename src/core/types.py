from __future__ import annotations

from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderClass(str, Enum):
    """Order class for resting protective legs held at the exchange.

    SIMPLE  -- a single order (default).
    BRACKET -- entry leg + take-profit (LIMIT) + stop-loss (STOP) legs as an
               OCO pair that arms once the entry fills.
    OCO     -- take-profit + stop-loss legs only, attached to an existing
               position (no entry leg). Values mirror Alpaca's order classes.
    """

    SIMPLE = "simple"
    BRACKET = "bracket"
    OCO = "oco"


class TimeFrame(str, Enum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1mo"

    @property
    def minutes(self) -> int:
        """Approximate duration of one bar of this timeframe, in minutes.

        Week is treated as 7 days and month as 30 days for ordering/comparison
        purposes; these are approximations, not calendar-exact.
        """
        return _TIMEFRAME_TO_MINUTES[self]


_TIMEFRAME_TO_MINUTES: dict[TimeFrame, int] = {
    TimeFrame.MINUTE_1: 1,
    TimeFrame.MINUTE_5: 5,
    TimeFrame.MINUTE_15: 15,
    TimeFrame.MINUTE_30: 30,
    TimeFrame.HOUR_1: 60,
    TimeFrame.HOUR_4: 240,
    TimeFrame.DAY_1: 1440,
    TimeFrame.WEEK_1: 1440 * 7,
    TimeFrame.MONTH_1: 1440 * 30,
}


# TimeFrames a batch interval may resolve to, finest first. Weekly/monthly are
# intentionally excluded: a batch interval should never resolve to a multi-day
# bar.
_BATCH_TIMEFRAMES: list[TimeFrame] = [
    TimeFrame.MINUTE_1,
    TimeFrame.MINUTE_5,
    TimeFrame.MINUTE_15,
    TimeFrame.MINUTE_30,
    TimeFrame.HOUR_1,
    TimeFrame.HOUR_4,
    TimeFrame.DAY_1,
]


def timeframe_from_minutes(minutes: int) -> TimeFrame:
    """Map a batch interval (in minutes) to the closest supported TimeFrame.

    Exact matches (5 -> 5m, 60 -> 1h, 1440 -> 1d, ...) return directly. For a
    value that does not correspond to a supported TimeFrame (e.g. 7), the
    nearest supported timeframe is chosen by absolute minute difference (ties
    favour the smaller/finer timeframe). The caller is expected to log a
    warning when the returned timeframe does not exactly match the requested
    interval.

    Args:
        minutes: Batch interval in minutes. Must be a positive integer.

    Returns:
        The exactly-matching or nearest supported TimeFrame.

    Raises:
        ValueError: If `minutes` is not a positive integer.
    """
    if minutes <= 0:
        raise ValueError(f"interval minutes must be positive, got {minutes}")

    for timeframe in _BATCH_TIMEFRAMES:
        if timeframe.minutes == minutes:
            return timeframe

    # No exact match: pick the supported timeframe with the smallest distance.
    # `min` is stable, so on a tie the earlier (finer) timeframe wins.
    return min(_BATCH_TIMEFRAMES, key=lambda tf: abs(tf.minutes - minutes))


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
