"""NewsPoller — intraday news diff for the scheduled-turn brief (FR-6, Q8=B).

Polls held + watched symbols on a background thread (TTL >= 15min, since the
provider caches ~15min anyway, C-6), keeps a persisted per-symbol last-seen
headline key so only *new* headlines surface, and is best-effort (a provider
failure/rate-limit never kills the daemon, NFR-4). News is brief-only, never a
wake trigger (latency is non-critical).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from src.agent.intraday.records import NewsDiff
from src.agent.steering.jsonl import atomic_write_text
from src.data.freshness import age_seconds
from src.data.news import fetch_news


class NewsPoller:
    def __init__(self, news_provider, root: str | Path, *, ttl_minutes: float = 15.0,
                 symbols_fn=None, limit: int = 8):
        self._np = news_provider
        self._seen_file = Path(root) / ".news_seen.json"
        self._ttl = ttl_minutes * 60.0
        self._symbols_fn = symbols_fn  # callable -> list[str] (held + watched)
        self._limit = limit
        self._seen: dict[str, str] = self._load_seen()
        self._diffs: dict[str, NewsDiff] = {}
        self._coverage: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._poll_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _load_seen(self) -> dict[str, str]:
        try:
            return json.loads(self._seen_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_seen(self) -> None:
        try:
            atomic_write_text(self._seen_file, json.dumps(self._seen))
        except Exception as e:
            logger.warning("news last-seen persist failed: {}", e)

    def poll_once(self, symbols) -> None:
        """Accumulate unread headlines until a turn takes them, even across polls."""
        if not self._poll_lock.acquire(blocking=False):
            return
        try:
            for sym in dict.fromkeys(symbols):
                result = fetch_news(self._np, sym, self._limit)
                articles = [{"title": it.title,
                             "published_at": it.published_at.isoformat() if getattr(it, "published_at", None) else None,
                             "link": getattr(it, "link", "")}
                            for it in result.items if getattr(it, "title", None)]
                with self._lock:
                    self._coverage[sym] = {**result.metadata(),
                                           "checked_at": datetime.now(UTC).isoformat(),
                                           "article_count": len(articles)}
                    if result.status != "ok" or not articles:
                        continue
                    new = []
                    for article in articles:
                        if article["title"] == self._seen.get(sym):
                            break
                        new.append(article)
                    if not new:
                        continue
                    prior = self._diffs.get(sym)
                    pending = {a["title"]: a for a in new}
                    for article in prior.articles if prior else []:
                        pending.setdefault(article["title"], article)
                    pending = list(pending.values())[:24]
                    self._diffs[sym] = NewsDiff(
                        symbol=sym, headlines=[a["title"] for a in pending], articles=pending,
                        last_seen_key=articles[0]["title"])
        finally:
            self._poll_lock.release()

    def diff_for(self, symbols) -> dict[str, NewsDiff]:
        with self._lock:
            result = {s: self._diffs.pop(s) for s in dict.fromkeys(symbols) if s in self._diffs}
            for sym, nd in result.items():
                self._seen[sym] = nd.last_seen_key
            if result:
                self._save_seen()
            return result

    def coverage_for(self, symbols) -> dict[str, dict]:
        with self._lock:
            result = {s: dict(self._coverage.get(s, {"status": "not_checked"})) for s in symbols}
        for row in result.values():
            age = age_seconds(row.get("fetched_at"))
            row["fetch_age_seconds"] = age
            if row["status"] == "ok" and (age is None or age > self._ttl + 30 or age < -5):
                row["status"] = "stale"
            elif row["status"] == "ok" and row.get("content_status") in {"old_only", "undated_or_future"}:
                row["status"] = "no_recent_dated_items"
        return result

    def refresh(self, symbols, *, timeout: float = 10.0) -> None:
        """Bound the turn's wait, with at most one outstanding refresh worker.

        A slow feed remains not_checked/stale in coverage; it cannot stall the
        model or spawn a new abandoned worker on every scheduled turn.
        """
        with self._lock:
            if self._refresh_thread is None or not self._refresh_thread.is_alive():
                self._refresh_thread = threading.Thread(
                    target=self.poll_once, args=(list(symbols),), name="news-refresh", daemon=True)
                self._refresh_thread.start()
            thread = self._refresh_thread
        thread.join(timeout=max(0.0, timeout))

    # ---- background thread ------------------------------------------------- #
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="news-poller", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                symbols = list(self._symbols_fn() if self._symbols_fn else [])
                if symbols:
                    self.poll_once(symbols)
            except Exception as e:  # belt-and-suspenders (NFR-4)
                logger.error("news poll loop error (continuing): {}", e)
            self._stop.wait(self._ttl)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
