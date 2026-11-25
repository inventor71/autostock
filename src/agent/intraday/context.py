"""The same compact research context for daemon and shadow scheduled turns."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from src.agent.intraday.bars import BarCache
from src.agent.intraday.brief import BriefAssembler
from src.agent.intraday.news_diff import NewsPoller
from src.agent.intraday.settings import IntradayConfig
from src.agent.intraday.util import held_and_watched
from src.agent.intraday.watch_store import WatchStore
from src.data.news import build_news_provider


def broker_snapshot(broker) -> dict:
    portfolio = broker.get_portfolio_state()
    snapshot = {"as_of": portfolio.timestamp.isoformat(),
                "equity": portfolio.equity, "cash": portfolio.cash,
                "positions": {s: p.model_dump(mode="json") for s, p in portfolio.positions.items()}}
    try:
        snapshot["open_orders"] = [o.model_dump(mode="json") for o in broker.get_open_orders()]
    except Exception as exc:  # noqa: BLE001 — broker failures become explicit missing-data status
        snapshot["open_orders_error"] = type(exc).__name__
    return snapshot


class IntradayContext:
    def __init__(self, data_provider, root, *, snapshot_fn, universe=(), state=None,
                 config=None, news_provider=None, sentiment_lines_fn=None):
        self.root = Path(root)
        self.snapshot_fn = snapshot_fn
        self.universe = set(universe)
        self.config = config or IntradayConfig()
        self.bars = BarCache(data_provider, bars_ttl=self.config.bars_cache_seconds,
                             price_ttl=self.config.price_cache_seconds)
        self.watch = WatchStore(root)
        self.news = NewsPoller(news_provider if news_provider is not None else build_news_provider(),
                               root, ttl_minutes=self.config.news_ttl_minutes,
                               symbols_fn=self.symbols)
        self.assembler = BriefAssembler(self.bars, state=state, watch_store=self.watch,
                                         sentiment_lines_fn=sentiment_lines_fn)

    def _symbols(self, snapshot):
        held_watch = held_and_watched(snapshot, self.watch)
        try:
            # Narrative mentions are observation candidates only. No trading
            # condition is inferred from prose; the structured WatchStore owns that.
            text = (self.root / "watchlist.md").read_text(encoding="utf-8")
        except OSError:
            text = ""
        mentioned = list(dict.fromkeys(s for s in re.findall(r"(?<![\w.-])[A-Z][A-Z0-9.-]*(?![\w.-])", text)
                                       if s in self.universe and s not in held_watch))
        symbols = list(dict.fromkeys([*held_watch, *self.config.market_symbols, *mentioned[:12]]))
        return symbols, [s for s in mentioned[12:] if s not in symbols]

    def symbols(self):
        return self._symbols(self.snapshot_fn())[0]

    def build(self, *, include_news=True) -> str:
        try:
            snapshot = self.snapshot_fn()
            if not snapshot:
                snapshot = {"account_error": "no_live_snapshot"}
        except Exception as exc:  # noqa: BLE001 — context must survive a failed account provider
            snapshot = {"account_error": type(exc).__name__}
        symbols, omitted = self._symbols(snapshot)
        news, coverage = None, None
        if include_news:
            self.news.refresh(symbols)
            news = self.news.diff_for(symbols)
            coverage = self.news.coverage_for(symbols)
        text = self.assembler.build(snapshot=snapshot, news=news, news_coverage=coverage,
                                     include_news=include_news, extra_symbols=symbols)
        if omitted:
            text += "\nWATCHLIST not refreshed (bounded scan): " + ", ".join(omitted)
        if include_news:
            record = {"as_of": datetime.now(UTC).isoformat(), "kind": "intraday",
                      "news": coverage, "market_data": {s: self.bars.coverage(s) for s in symbols},
                      "watchlist_not_refreshed": omitted,
                      "account_error": ((snapshot or {}).get("account_error")
                                        or (snapshot or {}).get("open_orders_error")
                                        or ("no_snapshot" if not snapshot else None)), "brief": text}
            self._record(record)
        return text

    def _record(self, record):
        """Separate research coverage from process/feed health, privately and locally."""
        tmp = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            text = json.dumps(record, ensure_ascii=False) + "\n"
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                             prefix=".research-context-", delete=False) as f:
                tmp = Path(f.name)
                f.write(text)
            tmp.replace(self.root / "research-context.json")
            fd = os.open(self.root / "research-context.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            logger.warning("Research context audit unavailable: {}", type(exc).__name__)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
