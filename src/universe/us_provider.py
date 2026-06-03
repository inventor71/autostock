"""US universe — S&P 100 constituents (dynamic via Wikipedia), optional market-cap cut.

Replaces the old static ``trading.symbols`` list. Both deps (pandas.read_html,
yfinance) are already in the project; the constituent table is parsed dynamically
and falls back to the committed snapshot offline.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.universe.base import BaseUniverseProvider

_SP100_URL = "https://en.wikipedia.org/wiki/S%26P_100"


class USUniverseProvider(BaseUniverseProvider):
    market = "us"

    def __init__(
        self,
        *,
        snapshot_path: str | Path = "config/universe/us_base.json",
        top_n: int = 100,
        rank_by_market_cap: bool = False,
        themes=None,
        enabled_themes=None,
        cache_ttl: float = 86_400.0,
    ):
        super().__init__(snapshot_path=snapshot_path, themes=themes,
                         enabled_themes=enabled_themes, cache_ttl=cache_ttl)
        self._top_n = top_n
        self._rank = rank_by_market_cap

    def _min_base(self) -> int:
        return 50

    @staticmethod
    def _normalize(symbol: str) -> str:
        # Wikipedia uses BRK.B; market-data providers use BRK.B too — keep as-is, upper.
        return symbol.strip().upper().replace(" ", "")

    def _fetch_base(self) -> list[str]:
        import pandas as pd

        tables = pd.read_html(_SP100_URL)
        for tbl in tables:
            cols = {str(c).strip().lower() for c in tbl.columns}
            if "symbol" in cols:
                syms = [self._normalize(s) for s in tbl[
                    [c for c in tbl.columns if str(c).strip().lower() == "symbol"][0]
                ].tolist()]
                syms = self._dedup(syms)
                if self._rank:
                    syms = self._marketcap_rank(syms)
                return syms[: self._top_n]
        return []

    def _marketcap_rank(self, symbols: list[str]) -> list[str]:
        try:
            import yfinance as yf

            caps: dict[str, float] = {}
            for s in symbols:
                try:
                    caps[s] = float(yf.Ticker(s).info.get("marketCap") or 0)
                except Exception:  # noqa: BLE001 — keep symbol, just unranked
                    caps[s] = 0.0
            return sorted(symbols, key=lambda s: caps.get(s, 0.0), reverse=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"US marketcap rank failed ({e}); keeping table order")
            return symbols
