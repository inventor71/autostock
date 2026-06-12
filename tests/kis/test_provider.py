"""Unit tests for KisDataProvider — mocked REST transport (no network, F30)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.core.exceptions import BrokerError
from src.core.types import TimeFrame
from src.data.providers.kis_provider import KisDataProvider


class FakeKis:
    def __init__(self, price="71000", bars=None, rt="0"):
        self._price = price
        self._rt = rt
        self._bars = bars if bars is not None else [
            {"stck_bsop_date": "20260601", "stck_oprc": "70000", "stck_hgpr": "71500",
             "stck_lwpr": "69800", "stck_clpr": "71000", "acml_vol": "1000000"},
            {"stck_bsop_date": "20260602", "stck_oprc": "71000", "stck_hgpr": "72000",
             "stck_lwpr": "70500", "stck_clpr": "71800", "acml_vol": "1200000"},
        ]
        self.gets = []

    def get(self, path, tr, params):
        self.gets.append((path, tr, params))
        if path.endswith("inquire-price"):
            return {"rt_cd": self._rt, "output": {"stck_prpr": self._price}}
        if path.endswith("inquire-daily-itemchartprice"):
            return {"rt_cd": self._rt, "output2": self._bars}
        return {"rt_cd": self._rt, "output": {}}


def make_dp(**kw):
    dp = KisDataProvider("ak", "sk")
    dp._c = FakeKis(**kw)
    return dp


def test_get_latest_price():
    assert make_dp(price="71000").get_latest_price("005930") == 71000.0


def test_get_latest_price_error_raises():
    with pytest.raises(BrokerError):
        make_dp(rt="1").get_latest_price("005930")


def test_get_bars_dataframe_shape_and_order():
    df = make_dp().get_bars("005930", TimeFrame.DAY_1, limit=10)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing
    assert len(df) == 2
    assert df.iloc[-1]["close"] == 71800.0 and df.iloc[-1]["volume"] == 1_200_000.0


def test_get_bars_respects_limit():
    bars = [{"stck_bsop_date": f"202605{d:02d}", "stck_oprc": "1", "stck_hgpr": "1",
             "stck_lwpr": "1", "stck_clpr": str(d), "acml_vol": "1"} for d in range(1, 21)]
    df = make_dp(bars=bars).get_bars("005930", TimeFrame.DAY_1, limit=5)
    assert len(df) == 5  # last 5 by date


def test_get_bars_empty_returns_empty_frame():
    df = make_dp(bars=[]).get_bars("005930", TimeFrame.DAY_1)
    assert df.empty and list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_minute_timeframe_falls_back_to_daily_period():
    dp = make_dp()
    dp.get_bars("005930", TimeFrame.MINUTE_5, limit=3)
    # falls back to daily period code "D" rather than crashing
    assert dp._c.gets[-1][2]["FID_PERIOD_DIV_CODE"] == "D"
