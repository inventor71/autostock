"""SignalCollector — the impure boundary that assembles the market-signal brief (F61).

Pulls price rows (reusing the existing scoreboard scan), news (Alpaca→yfinance),
and the earnings calendar (Finnhub), then calls the pure core. Every external
pull is wrapped best-effort and fail-honest: a failure degrades that one section
(recorded in ``degraded_sources``) and never crashes the research turn (NFR-1).
Results are TTL-cached so the push (prompt) and pull (tools) paths share one
collect (NFR-3).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Callable

from loguru import logger

from src.signals.brief import assemble_brief
from src.signals.earnings_cal import select_imminent_earnings
from src.signals.movers import detect_movers
from src.signals.peer_map import PeerMap
from src.signals.readthrough import build_readthrough
from src.signals.records import MarketSignalBrief, MoverRow
from src.signals.settings import SignalsConfig


def _norm(symbol: str) -> str:
    return symbol.strip().upper()


class SignalCollector:
    """Collect movers + read-through + imminent earnings into one brief.

    Injectable for tests: pass fakes for ``price_provider`` / ``news_provider`` /
    ``earnings_source``. Use :meth:`from_settings` to wire the real providers.
    """

    def __init__(
        self,
        *,
        config: SignalsConfig,
        universe: list[str],
        price_provider,
        news_provider=None,
        earnings_source=None,
        peer_map: PeerMap | None = None,
        held_provider: Callable[[], list[str]] | None = None,
    ):
        self.config = config
        self.universe = [_norm(s) for s in universe]
        self.price_provider = price_provider
        self.news_provider = news_provider
        self.earnings_source = earnings_source
        self.peer_map = peer_map or PeerMap.from_config(config.peer_groups)
        self.held_provider = held_provider
        self._cache: tuple[float, str, MarketSignalBrief] | None = None

    # -- public ----------------------------------------------------------- #
    def collect(
        self,
        *,
        today: date | None = None,
        held: list[str] | None = None,
        horizon_days: int | None = None,
    ) -> MarketSignalBrief:
        """Assemble the brief (TTL-cached). Never raises for source failures.

        ``horizon_days`` overrides the earnings horizon for this call only — it
        does NOT mutate ``self.config`` — and is part of the cache key so an
        override never returns a brief built for a different horizon.
        """
        today = today or date.today()
        if held is None and self.held_provider is not None:
            try:
                held = self.held_provider()
            except Exception as exc:  # held is best-effort context, not critical
                logger.warning("signals: held_provider failed: {}", exc)
                held = []
        held = held or []
        horizon = horizon_days if horizon_days is not None else self.config.earnings_horizon_days

        cache_key = (
            f"{today.isoformat()}|{horizon}|"
            f"{','.join(sorted(_norm(h) for h in held))}"
        )
        if self._cache is not None:
            cached_at, key, brief = self._cache
            if key == cache_key and (time.monotonic() - cached_at) < self.config.cache_ttl_seconds:
                return brief

        degraded: list[str] = []

        # 1. scan rows (price/volume) over universe ∪ bellwether watchlist
        scan_symbols = self._scan_symbols()
        rows = self._scan_rows(scan_symbols, degraded)

        # 2. movers (pure)
        universe_set = set(self.universe)
        movers = detect_movers(
            rows,
            price_pct=self.config.price_pct,
            vol_ratio=self.config.vol_ratio,
            universe=universe_set,
            require=self.config.require,
            max_movers=self.config.max_movers,
        )

        # 3. read-through (pure) + cause hints (best-effort news)
        alerts = build_readthrough(
            movers, self.peer_map, universe_set,
            min_trigger_pct=self.config.readthrough_min_pct,
            max_peers=self.config.max_peers,
        )
        self._attach_cause_hints(alerts, degraded)

        # 4. imminent earnings (best-effort source + pure selection)
        imminent = self._imminent_earnings(today, held, universe_set, degraded, horizon)

        brief = assemble_brief(movers, alerts, imminent, degraded)
        self._cache = (time.monotonic(), cache_key, brief)
        return brief

    # -- helpers ---------------------------------------------------------- #
    def _scan_symbols(self) -> list[str]:
        # Bellwethers are signal-only — enforce in-process (not just in the config
        # test): drop any that is also a tradeable universe symbol so it can never
        # be surfaced as an actionable read-through peer.
        uni = set(self.universe)
        watch = []
        for s in self.config.bellwether_watchlist:
            sn = _norm(s)
            if sn in uni:
                logger.warning(
                    "signals: bellwether {} is also in the tradeable universe — "
                    "treating as universe-only (not signal-only)", sn,
                )
                continue
            watch.append(sn)
        seen: set[str] = set()
        out: list[str] = []
        for s in self.universe + watch:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _scan_rows(self, symbols: list[str], degraded: list[str]) -> list[MoverRow]:
        import threading

        from src.agent.tools import market

        # yfinance has no per-call timeout, so bound the WHOLE scan: a slow/hung
        # backend must not stall the research turn (NFR-2). Run it on a DAEMON
        # thread and join with a deadline — a daemon worker can be abandoned on
        # timeout without leaking a non-daemon thread that blocks interpreter exit.
        box: dict = {}

        def _worker():
            try:
                box["raw"] = market.scoreboard(symbols, self.price_provider)
            except Exception as exc:  # captured, surfaced after join
                box["err"] = exc

        t = threading.Thread(target=_worker, name="signals-price-scan", daemon=True)
        t.start()
        t.join(self.config.scan_timeout_seconds)
        if t.is_alive():
            logger.warning(
                "signals: price scan exceeded {}s budget — degrading",
                self.config.scan_timeout_seconds,
            )
            degraded.append("prices:timeout")
            return []
        if "err" in box:
            logger.warning("signals: scoreboard scan failed: {}", box["err"])
            degraded.append("prices:scoreboard")
            return []
        raw = box.get("raw", [])
        rows: list[MoverRow] = []
        for r in raw:
            if r.get("error"):
                continue
            rows.append(
                MoverRow(
                    symbol=r.get("symbol", ""),
                    change_pct=r.get("chg_1d"),
                    volume_ratio=r.get("vol_ratio"),
                    close=r.get("close"),
                )
            )
        return rows

    def _attach_cause_hints(self, alerts, degraded: list[str]) -> None:
        if not alerts or self.news_provider is None:
            return
        failed = False
        # Cap the fan-out: only the strongest triggers get a news lookup, so a
        # volatile day with many alerts can't run an unbounded number of calls.
        for alert in alerts[: self.config.max_cause_hint_lookups]:
            try:
                items = self.news_provider.get_news(alert.trigger_symbol, limit=3)
            except Exception as exc:
                if not failed:
                    logger.warning("signals: news lookup failed: {}", exc)
                    failed = True
                continue
            if items and getattr(items[0], "title", None):
                hint = items[0].title.strip()
                alert.cause_hint = hint[:120]
        if failed:
            degraded.append("news")

    def _imminent_earnings(self, today, held, universe_set, degraded: list[str], horizon: int):
        if self.earnings_source is None:
            degraded.append("earnings:disabled")
            return []
        from datetime import timedelta

        try:
            cal = self.earnings_source.get_calendar(today, today + timedelta(days=horizon))
        except Exception as exc:
            logger.warning("signals: earnings calendar failed: {}", exc)
            degraded.append("earnings:finnhub")
            return []
        return select_imminent_earnings(
            cal, universe_set, {_norm(h) for h in held}, self.peer_map,
            horizon_days=horizon, today=today,
        )

    # -- wiring ----------------------------------------------------------- #
    @classmethod
    def from_settings(
        cls,
        *,
        price_provider=None,
        held_provider: Callable[[], list[str]] | None = None,
    ) -> "SignalCollector":
        """Wire the real providers/sources from ``config/settings.yaml`` + env."""
        from config.config import get_settings

        settings = get_settings()
        config = SignalsConfig.from_settings(settings.signals)
        universe = list(settings.trading.symbols)

        if price_provider is None:
            from src.data.providers.yfinance_provider import YFinanceProvider

            price_provider = YFinanceProvider()

        news_provider = _build_news_provider(config, settings)
        earnings_source = _build_earnings_source(config, settings)

        return cls(
            config=config,
            universe=universe,
            price_provider=price_provider,
            news_provider=news_provider,
            earnings_source=earnings_source,
            held_provider=held_provider,
        )


def _build_news_provider(config: SignalsConfig, settings):
    """Alpaca primary (Benzinga) with yfinance fallback, per config. Fail-honest:
    if the primary can't be built, fall back; if neither, return None."""
    primary = config.sources.news_primary
    if primary == "alpaca" and settings.alpaca_api_key and settings.alpaca_api_secret:
        try:
            from src.signals.sources.alpaca_news import AlpacaNewsProvider

            return AlpacaNewsProvider(
                settings.alpaca_api_key, settings.alpaca_api_secret,
                http_connect_timeout=config.http_connect_timeout,
                http_read_timeout=config.http_read_timeout,
            )
        except Exception as exc:
            logger.warning("signals: Alpaca news unavailable, falling back: {}", exc)
    if config.sources.news_fallback == "yfinance" or primary == "yfinance":
        from src.data.providers.news_provider import YFinanceNewsProvider

        return YFinanceNewsProvider()
    return None


def _build_earnings_source(config: SignalsConfig, settings):
    """Finnhub calendar when configured + keyed; else None (fail-honest)."""
    if config.sources.earnings_provider != "finnhub":
        return None
    key = getattr(settings, "finnhub_api_key", "")
    if not key:
        logger.info("signals: FINNHUB_API_KEY not set — earnings calendar disabled")
        return None
    try:
        from src.signals.sources.finnhub_earnings import FinnhubEarningsCalendar

        return FinnhubEarningsCalendar(
            key,
            http_connect_timeout=config.http_connect_timeout,
            http_read_timeout=config.http_read_timeout,
        )
    except Exception as exc:
        logger.warning("signals: Finnhub earnings unavailable: {}", exc)
        return None
