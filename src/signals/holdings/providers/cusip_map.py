"""CUSIP → ticker mapping (F81) — isolated so the strategy is swappable.

13F reports positions by CUSIP; the bot trades by ticker. We map with a local,
offline, deterministic table (``config/holdings/cusip_ticker.json``) seeded with
the common large-caps + the names a 13F like Situational Awareness LP holds.
Unmapped CUSIPs are dropped by the caller and counted (``unmapped_n``) — we never
invent a ticker. A paid/contracted CUSIP service could replace this table later
without touching anything outside this provider (the design's extension point).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

_DEFAULT_MAP = "config/holdings/cusip_ticker.json"


def _normalize_cusip(cusip: str) -> str:
    return (cusip or "").strip().upper()


@lru_cache(maxsize=4)
def _load_map(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        logger.warning("holdings: CUSIP map {} missing — all rows will be unmapped", path)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — bad map degrades to empty, never raises
        logger.warning("holdings: CUSIP map {} unreadable ({})", path, exc)
        return {}
    out: dict[str, str] = {}
    for cusip, ticker in (raw or {}).items():
        if isinstance(cusip, str) and isinstance(ticker, str) and ticker.strip():
            out[_normalize_cusip(cusip)] = ticker.strip().upper()
    return out


class CusipMapper:
    """Look up a ticker for a CUSIP. Both 9- and 8-char (no check digit) keys hit."""

    def __init__(self, map_path: str = _DEFAULT_MAP):
        self._map_path = map_path

    def lookup(self, cusip: str) -> str | None:
        c = _normalize_cusip(cusip)
        if not c:
            return None
        m = _load_map(self._map_path)
        if c in m:
            return m[c]
        # 13F CUSIPs are 9 chars (incl. check digit); some tables key on the 8-char
        # issuer+issue stem — try that too before giving up.
        if len(c) == 9 and c[:8] in m:
            return m[c[:8]]
        return None
