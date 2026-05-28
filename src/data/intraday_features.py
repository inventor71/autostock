"""Deterministic intraday-shape features for one trading session (P0).

Pure functions only — no I/O, no network. Given one symbol's intraday OHLCV bars
for a single session (plus the prior session's close), ``compute_session_features``
returns a flat dict capturing the day's shape: overnight gap, opening-range move,
where the high/low landed in time, drawup/drawdown from the open, where the close
sat in the range, VWAP deviation, and realized intraday volatility.

These are the raw, backtestable observations the P0 analysis layer aggregates to
answer "do the conjectured intraday patterns statistically exist and persist?".
Thresholded pattern *labels* are intentionally NOT computed here — they belong in
the analysis layer so their cutoffs stay tunable.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

# Stable on-disk / DataFrame column order shared with the store and analysis.
FEATURE_COLUMNS: list[str] = [
    "date",
    "symbol",
    "prev_close",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "bar_count",
    "gap_pct",
    "or_ret",
    "or_range_pct",
    "oc_ret",
    "last30_ret",
    "vwap",
    "vwap_dev_close",
    "hi_t_min",
    "lo_t_min",
    "max_drawup_pct",
    "max_drawdown_pct",
    "close_loc",
    "realized_vol",
]

_PRICE_DP = 4
_RATIO_DP = 6


def _ratio(numer: float, denom: float) -> float | None:
    """``numer / denom - 1`` as a rounded ratio, or None when undefined."""
    if denom is None or denom == 0:
        return None
    return round(numer / denom - 1.0, _RATIO_DP)


def _minutes_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return int(round((end - start).total_seconds() / 60.0))


def compute_session_features(
    bars: pd.DataFrame,
    *,
    symbol: str,
    session_date: date,
    prev_close: float | None,
    open_range_minutes: int = 30,
    last_minutes: int = 30,
) -> dict:
    """Compute the intraday-shape feature record for a single session.

    Args:
        bars: Intraday OHLCV bars for ONE session, ascending DatetimeIndex with
            columns open/high/low/close/volume (the shape returned by
            ``BaseDataProvider.get_bars``). tz-aware or tz-naive both work.
        symbol: Ticker (stored upper-cased).
        session_date: The calendar date this session belongs to.
        prev_close: Prior session's close, used for the overnight gap; None when
            unknown (e.g. the first session in a backfill) -> ``gap_pct`` is None.
        open_range_minutes: Opening-range window, measured from the first bar's
            timestamp (exclusive upper bound).
        last_minutes: Trailing window for ``last30_ret``.

    Returns:
        A flat dict keyed by ``FEATURE_COLUMNS``.

    Raises:
        ValueError: If ``bars`` is empty (fail-closed; the collector skips/logs).
    """
    if bars is None or bars.empty:
        raise ValueError(f"no intraday bars for {symbol} on {session_date}")

    bars = bars.sort_index()
    o = float(bars["open"].iloc[0])
    c = float(bars["close"].iloc[-1])
    hi = float(bars["high"].max())
    lo = float(bars["low"].min())
    volume = int(bars["volume"].sum())
    first_ts = bars.index[0]
    last_ts = bars.index[-1]

    # Opening range: bars strictly within [open, open + open_range_minutes).
    or_window = bars[bars.index < first_ts + timedelta(minutes=open_range_minutes)]
    if not or_window.empty:
        or_end = float(or_window["close"].iloc[-1])
        or_ret = _ratio(or_end, o)
        or_hi = float(or_window["high"].max())
        or_lo = float(or_window["low"].min())
        or_range_pct = round((or_hi - or_lo) / o, _RATIO_DP) if o else None
    else:  # pragma: no cover - single-bar session
        or_ret = None
        or_range_pct = None

    # Last-N-minute return: close vs the last bar at/under (last_ts - last_minutes).
    ref_window = bars[bars.index <= last_ts - timedelta(minutes=last_minutes)]
    last30_ret = _ratio(c, float(ref_window["close"].iloc[-1])) if not ref_window.empty else None

    # VWAP from per-bar typical price.
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    vol = bars["volume"]
    total_vol = float(vol.sum())
    vwap = float((typical * vol).sum() / total_vol) if total_vol > 0 else c

    # Time (minutes from open) of the session high and low.
    hi_t = _minutes_between(first_ts, bars["high"].idxmax())
    lo_t = _minutes_between(first_ts, bars["low"].idxmin())

    close_loc = round((c - lo) / (hi - lo), _RATIO_DP) if hi > lo else 0.5
    realized_vol = bars["close"].pct_change().std()
    realized_vol = round(float(realized_vol), _RATIO_DP) if pd.notna(realized_vol) else None

    return {
        "date": session_date.isoformat(),
        "symbol": symbol.upper(),
        "prev_close": round(prev_close, _PRICE_DP) if prev_close is not None else None,
        "open": round(o, _PRICE_DP),
        "high": round(hi, _PRICE_DP),
        "low": round(lo, _PRICE_DP),
        "close": round(c, _PRICE_DP),
        "volume": volume,
        "bar_count": int(len(bars)),
        "gap_pct": _ratio(o, prev_close) if prev_close is not None else None,
        "or_ret": or_ret,
        "or_range_pct": or_range_pct,
        "oc_ret": _ratio(c, o),
        "last30_ret": last30_ret,
        "vwap": round(vwap, _PRICE_DP),
        "vwap_dev_close": _ratio(c, vwap),
        "hi_t_min": hi_t,
        "lo_t_min": lo_t,
        "max_drawup_pct": round((hi - o) / o, _RATIO_DP) if o else None,
        "max_drawdown_pct": round((lo - o) / o, _RATIO_DP) if o else None,
        "close_loc": close_loc,
        "realized_vol": realized_vol,
    }
