"""Universe providers — how the tradeable symbol pool is obtained.

A universe = a dynamic *base* (market-derived) ∪ user-configured *themes*. The base
is cached (1 day) and falls back to a committed snapshot so the pool is always
non-empty offline; an empty universe is fail-closed (``UniverseError``) so trading
never starts on nothing.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from src.core.exceptions import AutostockError


class UniverseError(AutostockError):
    """No usable universe (dynamic fetch and snapshot both empty) — fail-closed."""


class BaseUniverseProvider(ABC):
    market: str = ""

    def __init__(
        self,
        *,
        snapshot_path: str | Path,
        themes: dict[str, list[str]] | None = None,
        enabled_themes: list[str] | None = None,
        cache_ttl: float = 86_400.0,
    ):
        self._snapshot_path = Path(snapshot_path)
        self._themes = themes or {}
        self._enabled = list(enabled_themes or [])
        self._cache_ttl = cache_ttl
        self._base_cache: list[str] | None = None
        self._base_ts = 0.0

    # -- public --------------------------------------------------------- #
    def get_symbols(self) -> list[str]:
        symbols = set(self._cached_base())
        for name in self._enabled:
            members = self._themes.get(name)
            if not members:
                logger.warning(f"universe theme '{name}' is empty/undefined; ignoring")
                continue
            symbols.update(self._normalize(s) for s in members)
        if not symbols:
            raise UniverseError(f"{self.market or 'universe'}: empty (no base, no snapshot)")
        return sorted(symbols)

    # -- base + cache + snapshot --------------------------------------- #
    def _cached_base(self) -> list[str]:
        if self._base_cache is not None and (time.time() - self._base_ts) < self._cache_ttl:
            return self._base_cache
        try:
            fetched = [self._normalize(s) for s in self._fetch_base()]
            fetched = self._dedup(fetched)
            if self._sane(fetched):
                self._save_snapshot(fetched)
                self._base_cache, self._base_ts = fetched, time.time()
                return fetched
            logger.warning(f"{self.market}: dynamic base too small ({len(fetched)}); using snapshot")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{self.market}: base fetch failed ({e}); using snapshot")
        snap = self._load_snapshot()
        self._base_cache, self._base_ts = snap, time.time()
        return snap

    @abstractmethod
    def _fetch_base(self) -> list[str]:
        """Dynamic base symbols for this market (market-cap rank / index list)."""

    def _sane(self, symbols: list[str]) -> bool:
        """Guard against a degenerate dynamic response polluting the snapshot."""
        return len(symbols) >= self._min_base()

    def _min_base(self) -> int:
        return 1

    # -- helpers -------------------------------------------------------- #
    @staticmethod
    def _normalize(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _dedup(symbols: list[str]) -> list[str]:
        return list(dict.fromkeys(s for s in symbols if s))

    def _save_snapshot(self, symbols: list[str]) -> None:
        try:
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_path.write_text(json.dumps(symbols, ensure_ascii=False, indent=2))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{self.market}: snapshot save failed ({e})")

    def _load_snapshot(self) -> list[str]:
        if not self._snapshot_path.exists():
            return []
        try:
            return self._dedup(self._normalize(s) for s in json.loads(self._snapshot_path.read_text()))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{self.market}: snapshot load failed ({e})")
            return []
