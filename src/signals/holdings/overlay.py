"""Universe overlay from disclosed holdings — source-agnostic, direction-gated (F81).

Turns cached :class:`HoldingsSnapshot`\\ s into the set of tickers to *union* into
the tradeable universe. Two hard rules (FR-4, comply with the existing short stack
F54/F60):

- **LONG** holdings are always eligible (long candidates).
- **SHORT** holdings (e.g. 13F puts) are eligible ONLY when ``shorting_enabled`` is
  true. With shorting off (the shipped default) a bearish name is NOT added to the
  universe — it stays brief-only context, so a PUT can never be mis-read as a long
  candidate. Even when added, the actual short still passes the unchanged
  ``RiskManager`` gate (ETB/halts/stop); the overlay only makes a name *eligible*.

Stale snapshots (filing older than ``max_age_days``) and sources whose ``overlay``
flag is off are excluded. The function is pure; the caller does the I/O and unions
the result into ``base ∪ themes``.
"""

from __future__ import annotations

from datetime import date

from src.signals.holdings.records import HoldingsSnapshot
from src.signals.holdings.store import is_stale


def holdings_universe_overlay(
    snapshots: list[HoldingsSnapshot],
    overlay_source_ids: set[str],
    *,
    shorting_enabled: bool,
    max_age_days: int,
    today: date | None = None,
) -> list[str]:
    """Sorted, de-duplicated tickers to add to the tradeable universe.

    ``overlay_source_ids`` is the allowlist of sources whose config opted into the
    universe overlay (others are brief-only). Empty inputs → empty list (the
    universe is unchanged — union-only, never removes a base/theme symbol).
    """
    out: set[str] = set()
    for snap in snapshots:
        if snap.source_id not in overlay_source_ids:
            continue
        if is_stale(snap, max_age_days=max_age_days, today=today):
            continue
        out.update(snap.long_tickers())
        if shorting_enabled:
            out.update(snap.short_tickers())
    return sorted(out)
