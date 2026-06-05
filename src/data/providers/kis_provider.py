"""KIS (한국투자증권) Korean-equity market-data provider over the 모의/실전 REST domain.

Shares the raw-REST transport rationale with ``KisBroker`` (pykis routes
market-data to the real domain → unusable with virtual-only keys). Daily/weekly/
monthly OHLCV via inquire-daily-itemchartprice; current price via inquire-price.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

from src.core.exceptions import BrokerError
from src.core.types import TimeFrame
from src.data.base import BaseDataProvider
from src.execution.brokers.kis_rest import KisRestClient

_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_DAILY_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

# autostock TimeFrame -> KIS FID_PERIOD_DIV_CODE (daily-and-coarser only).
_PERIOD_CODE = {TimeFrame.DAY_1: "D", TimeFrame.WEEK_1: "W", TimeFrame.MONTH_1: "M"}


def _f(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key)
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


class KisDataProvider(BaseDataProvider):
    def __init__(
        self,
        appkey: str,
        appsecret: str,
        *,
        paper: bool = True,
        connect_timeout: float = 3.0,
        read_timeout: float = 5.0,
        rate_limit_per_sec: float = 2.0,
        client: KisRestClient | None = None,
    ):
        # Reuse a broker's client if provided (shared token/throttle), else own one.
        self._c = client or KisRestClient(
            appkey, appsecret, paper=paper,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            rate_limit_per_sec=rate_limit_per_sec,
        )

    @staticmethod
    def _iscd(symbol: str) -> str:
        return symbol.strip().upper()

    def get_latest_price(self, symbol: str) -> float:
        res = self._c.get(_PRICE_PATH, "FHKST01010100",
                          {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": self._iscd(symbol)})
        if res.get("rt_cd") != "0":
            raise BrokerError(f"KIS price inquiry failed [{res.get('msg_cd')}]: {res.get('msg1')}")
        return _f(res.get("output") or {}, "stck_prpr")

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.DAY_1,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        period = _PERIOD_CODE.get(timeframe)
        if period is None:
            logger.warning(f"KIS get_bars: {timeframe} unsupported (minute bars TODO); using daily")
            period = "D"
        end = end or datetime.now()
        # KIS returns up to 100 bars in [date_1, date_2]; widen the window for coarser periods.
        span_days = {"D": 1, "W": 7, "M": 31}.get(period, 1) * max(limit, 1) + 10
        start = start or (end - timedelta(days=span_days))
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": self._iscd(symbol),
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": period, "FID_ORG_ADJ_PRC": "0",
        }
        res = self._c.get(_DAILY_CHART_PATH, "FHKST03010100", params)
        if res.get("rt_cd") != "0":
            raise BrokerError(f"KIS chart inquiry failed [{res.get('msg_cd')}]: {res.get('msg1')}")
        rows = res.get("output2") or []
        bars = []
        for r in rows:
            date = r.get("stck_bsop_date")
            if not date:
                continue
            bars.append({
                "timestamp": pd.to_datetime(date, format="%Y%m%d"),
                "open": _f(r, "stck_oprc"), "high": _f(r, "stck_hgpr"),
                "low": _f(r, "stck_lwpr"), "close": _f(r, "stck_clpr"),
                "volume": _f(r, "acml_vol"),
            })
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(bars).set_index("timestamp").sort_index()
        return df.tail(limit)
