"""IntradayConfig — tunables for the F3 intraday redesign (config/settings.yaml
``intraday:`` block, Q4(i)). Defaults are the fail-safe when the block is absent.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agent.intraday.abnormal import AbnormalConfig


@dataclass(frozen=True)
class IntradayConfig:
    atr_k: float = 1.5
    vol_multiple: float = 3.0
    atr_period: int = 14
    wake_detect_seconds: int = 5
    wake_timeout: float = 120.0
    news_ttl_minutes: float = 15.0
    bars_cache_seconds: float = 60.0
    price_cache_seconds: float = 3.0

    @classmethod
    def from_mapping(cls, m: dict | None) -> "IntradayConfig":
        """Build from a (possibly nested) settings mapping; unknown keys ignored."""
        if not m:
            return cls()
        abn = m.get("abnormal_move", {}) or {}
        wake = m.get("wake", {}) or {}
        news = m.get("news", {}) or {}
        bars = m.get("bars", {}) or {}
        price = m.get("price", {}) or {}
        d = cls()
        return cls(
            atr_k=float(abn.get("atr_k", d.atr_k)),
            vol_multiple=float(abn.get("vol_multiple", d.vol_multiple)),
            atr_period=int(abn.get("atr_period", d.atr_period)),
            wake_detect_seconds=int(wake.get("detect_seconds", d.wake_detect_seconds)),
            wake_timeout=float(wake.get("timeout", d.wake_timeout)),
            news_ttl_minutes=float(news.get("ttl_minutes", d.news_ttl_minutes)),
            bars_cache_seconds=float(bars.get("cache_seconds", d.bars_cache_seconds)),
            price_cache_seconds=float(price.get("cache_seconds", d.price_cache_seconds)),
        )

    def abnormal(self) -> AbnormalConfig:
        return AbnormalConfig(atr_k=self.atr_k, vol_multiple=self.vol_multiple,
                              atr_period=self.atr_period)
