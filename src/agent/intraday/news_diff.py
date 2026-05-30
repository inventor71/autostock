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
from pathlib import Path

from loguru import logger

from src.agent.intraday.records import NewsDiff
from src.agent.steering.jsonl import atomic_write_text


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
        """Fetch each symbol's headlines and record only those newer than the
        persisted last-seen key. Best-effort per symbol."""
        for sym in symbols:
            try:
                items = self._np.get_news(sym, limit=self._limit)
            except Exception as e:
                logger.warning("news fetch failed for {} (skipping): {}", sym, e)
                continue
            headlines = [it.title for it in items if getattr(it, "title", None)]
            if not headlines:
                self._diffs.pop(sym, None)
                continue
            last = self._seen.get(sym)
            new = []
            for h in headlines:  # newest-first; stop at the previously-seen boundary
                if h == last:
                    break
                new.append(h)
            self._seen[sym] = headlines[0]
            if new:
                self._diffs[sym] = NewsDiff(symbol=sym, headlines=new, last_seen_key=headlines[0])
            else:
                self._diffs.pop(sym, None)
        self._save_seen()

    def diff_for(self, symbols) -> dict[str, NewsDiff]:
        return {s: self._diffs[s] for s in symbols if s in self._diffs}

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
