"""KR universe — KOSPI200 + KOSDAQ(top-N) by market cap via KIS ranking.

KIS has no clean KOSPI200/KOSDAQ150 *constituent-list* endpoint, but the market-cap
ranking (FHPST01740000) takes ``FID_INPUT_ISCD=2001`` (코스피200) directly and
``1001`` (코스닥, take top-N) — a dynamic proxy for the index universe.
"""

from __future__ import annotations

from pathlib import Path

from src.execution.brokers.kis_rest import KisRestClient
from src.universe.base import BaseUniverseProvider

_RANK_PATH = "/uapi/domestic-stock/v1/ranking/market-cap"
_RANK_TR = "FHPST01740000"


class KRUniverseProvider(BaseUniverseProvider):
    """Dynamic KR base = top-N KOSPI + top-N KOSDAQ by market cap.

    The KIS market-cap ranking returns a fixed **top-30 per market per call** and
    does not paginate, so the dynamic base is the ~60 most-liquid KR names (a
    focused, tradeable universe). For broader breadth, edit the committed snapshot.
    """

    market = "kr"

    def __init__(
        self,
        client: KisRestClient,
        *,
        snapshot_path: str | Path = "config/universe/kr_base.json",
        kospi_n: int = 30,    # the ranking endpoint caps at ~30/market (no paging)
        kosdaq_n: int = 30,
        themes=None,
        enabled_themes=None,
        cache_ttl: float = 86_400.0,
    ):
        super().__init__(snapshot_path=snapshot_path, themes=themes,
                         enabled_themes=enabled_themes, cache_ttl=cache_ttl)
        self._c = client
        self._kospi_n = kospi_n
        self._kosdaq_n = kosdaq_n

    def _min_base(self) -> int:
        # Accept the dynamic result when both markets returned roughly their cap;
        # otherwise (rate-limited/partial) fall back to the snapshot.
        return max(10, (min(self._kospi_n, 30) + min(self._kosdaq_n, 30)) // 2)

    def _rank(self, iscd: str, n: int) -> list[str]:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20174",
            "FID_DIV_CLS_CODE": "0", "FID_INPUT_ISCD": iscd,
            "FID_TRGT_CLS_CODE": "0", "FID_TRGT_EXLS_CLS_CODE": "0",
            "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "", "FID_VOL_CNT": "",
        }
        res = self._c.get(_RANK_PATH, _RANK_TR, params)
        if res.get("rt_cd") != "0":
            return []
        out = res.get("output") or []
        codes = [row.get("mksc_shrn_iscd") or row.get("stck_shrn_iscd", "") for row in out]
        return [c for c in codes if c][:n]

    def _fetch_base(self) -> list[str]:
        return self._rank("2001", self._kospi_n) + self._rank("1001", self._kosdaq_n)
