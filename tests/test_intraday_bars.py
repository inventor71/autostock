"""Step 5 — BarCache routing + pure abnormal-move (example + Hypothesis PBT)."""

from __future__ import annotations

import pandas as pd
from hypothesis import given, strategies as st

from src.agent.intraday.abnormal import (
    AbnormalConfig,
    breaches_atr,
    breaches_volume,
    detect_abnormal,
)
from src.agent.intraday.bars import BarCache, atr, avg_volume


def _bars(highs, lows, closes, vols):
    idx = pd.date_range("2026-05-30 09:30", periods=len(closes), freq="5min")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": vols}, index=idx)


class _CountingProvider:
    def __init__(self):
        self.bar_calls = 0
        self.price_calls = 0

    def get_bars(self, symbol, timeframe=None, limit=50):
        self.bar_calls += 1
        return _bars([101, 102], [99, 100], [100, 101], [10, 12])

    def get_latest_price(self, symbol):
        self.price_calls += 1
        return 101.0


# ---- pure indicators ------------------------------------------------------- #
def test_atr_and_avg_volume_example():
    bars = _bars([110, 112, 111], [100, 101, 103], [105, 108, 107], [100, 200, 300])
    a = atr(bars, period=14)
    assert a is not None and a > 0
    # excludes the current (last) bar from its own baseline (review #6): mean(100,200)
    assert avg_volume(bars) == 150.0


def test_atr_none_when_insufficient():
    assert atr(_bars([1], [1], [1], [1])) is None
    assert atr(None) is None


# ---- BarCache routing ------------------------------------------------------ #
def test_bar_cache_serves_from_cache_within_ttl():
    p = _CountingProvider()
    cache = BarCache(p, bars_ttl=999, price_ttl=999)
    cache.get_bars("AAPL")
    cache.get_bars("AAPL")
    assert p.bar_calls == 1  # second read served from cache (no sync fetch)
    cache.get_price("AAPL")
    cache.get_price("AAPL")
    assert p.price_calls == 1


def test_bar_cache_returns_cached_on_fetch_failure():
    class _Flaky:
        def __init__(self):
            self.n = 0

        def get_bars(self, symbol, timeframe=None, limit=50):
            self.n += 1
            if self.n == 1:
                return _bars([101, 102], [99, 100], [100, 101], [10, 12])
            raise RuntimeError("rate limited")

        def get_latest_price(self, symbol):
            raise RuntimeError("down")

    cache = BarCache(_Flaky(), bars_ttl=0, price_ttl=0)  # always stale -> refetch
    first = cache.get_bars("AAPL")
    assert first is not None
    assert cache.get_bars("AAPL") is first  # failure -> last cached, never raises
    assert cache.get_price("AAPL") is None  # no cached price, failure -> None


# ---- detect_abnormal ------------------------------------------------------- #
def test_detect_abnormal_price_breach():
    bars = _bars([101, 102], [99, 100], [100, 101], [10, 12])  # small ATR ~ 2
    sig = detect_abnormal("AAPL", price=110.0, ref_price=100.0, bars=bars,
                          cfg=AbnormalConfig(atr_k=1.5, vol_multiple=99))
    assert sig is not None and sig.kind == "price"


def test_detect_abnormal_volume_breach():
    # avg(10,10,10,10,1000)=208; last 1000 > 3*208 -> volume breach.
    bars = _bars([101] * 5, [99] * 5, [100] * 5, [10, 10, 10, 10, 1000])
    sig = detect_abnormal("AAPL", price=100.2, ref_price=100.0, bars=bars,
                          cfg=AbnormalConfig(atr_k=99, vol_multiple=3))
    assert sig is not None and sig.kind == "volume"


def test_detect_abnormal_none():
    bars = _bars([101, 102], [99, 100], [100, 101], [10, 12])
    assert detect_abnormal("AAPL", 100.1, 100.0, bars,
                           AbnormalConfig(atr_k=99, vol_multiple=99)) is None


# ---- PBT (pure threshold predicates) --------------------------------------- #
@given(move=st.floats(min_value=0, max_value=1e6, allow_nan=False),
       atr_value=st.floats(min_value=0.01, max_value=1e4, allow_nan=False),
       k=st.floats(min_value=0.01, max_value=10, allow_nan=False),
       extra=st.floats(min_value=0, max_value=1e6, allow_nan=False))
def test_breaches_atr_monotonic_in_move(move, atr_value, k, extra):
    # If a move breaches, any larger-magnitude move also breaches (monotone).
    if breaches_atr(move, atr_value, k):
        assert breaches_atr(move + extra, atr_value, k)


@given(atr_value=st.floats(min_value=0.01, max_value=1e4, allow_nan=False),
       k=st.floats(min_value=0.01, max_value=10, allow_nan=False))
def test_breaches_atr_boundary_is_strict(atr_value, k):
    # Exactly at the threshold is NOT a breach (strict >).
    assert breaches_atr(k * atr_value, atr_value, k) is False


@given(volume=st.floats(min_value=0, max_value=1e9, allow_nan=False),
       avg=st.floats(min_value=0.01, max_value=1e7, allow_nan=False),
       m=st.floats(min_value=0.01, max_value=20, allow_nan=False),
       extra=st.floats(min_value=0, max_value=1e9, allow_nan=False))
def test_breaches_volume_monotonic(volume, avg, m, extra):
    if breaches_volume(volume, avg, m):
        assert breaches_volume(volume + extra, avg, m)
