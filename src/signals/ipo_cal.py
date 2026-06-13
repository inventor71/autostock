"""Imminent-IPO selection — pure (F78, FR-2).

Unlike :mod:`src.signals.earnings_cal`, this does **not** filter to the tradeable
universe: an IPO is by definition a name not yet on the menu, and the whole point
of the awareness channel is to surface it anyway. The universe/held sets only TAG
a row (a recent IPO already added to the universe) — they never drop one.

Withdrawn IPOs are dropped (they won't list). Rows are ranked by size
(``est_value`` desc, missing last) so a flood of micro-cap listings can't crowd
out the one that moves the market, then capped at ``max_ipos``.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.signals.records import ImminentIpo, IpoRow


def _norm(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    s = symbol.strip().upper()
    return s or None


def select_imminent_ipos(
    rows: list[IpoRow],
    *,
    today: date,
    horizon_days: int,
    max_ipos: int,
    universe: set[str] | None = None,
    held: set[str] | None = None,
) -> list[ImminentIpo]:
    """Return upcoming IPOs within ``[today, today+horizon]``, size-ranked + capped.

    Pure: same inputs → same output. ``withdrawn`` rows are excluded;
    ``in_universe`` / ``is_held`` are tags (not filters).
    """
    uni = {s.strip().upper() for s in (universe or set())}
    held_n = {s.strip().upper() for s in (held or set())}
    horizon_end = today + timedelta(days=horizon_days)

    out: list[ImminentIpo] = []
    for row in rows:
        if row.status == "withdrawn":
            continue
        if not (today <= row.ipo_date <= horizon_end):
            continue
        sym = _norm(row.symbol)
        out.append(
            ImminentIpo(
                name=row.name,
                symbol=sym,
                ipo_date=row.ipo_date,
                exchange=row.exchange,
                status=row.status,
                est_value=row.est_value,
                in_universe=sym is not None and sym in uni,
                is_held=sym is not None and sym in held_n,
            )
        )

    # Size desc (None last), then soonest, then name — deterministic.
    out.sort(
        key=lambda e: (
            e.est_value is None,
            -(e.est_value or 0.0),
            e.ipo_date,
            e.name,
        )
    )
    return out[:max_ipos]
