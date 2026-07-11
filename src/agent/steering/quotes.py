"""F95: latest-quote warm cache + click-candidate selection for the symbol panel.

The operator console's SymbolOverlay shows a live quote the instant a symbol is
clicked. The TUI is file-only (no request channel to the daemon), so the daemon
keeps a small set of *candidate* symbols warm — held ∪ resting-order ∪ recently
decided/intervened — refreshed on a short cadence and published to
``steering/quotes.json``. The TUI then reads the clicked symbol's price directly.

Two account-independent pieces live here (both pure, unit-testable without a
broker): the ``QuoteBook`` cache and the ``quote_candidates`` selector. The fetch
itself uses the shared data provider (not the broker's marking price) so quotes
are the same real-market facts regardless of which account an instance trades —
see the F95 requirements ADR. A single daemon polls only its own candidates over
plain REST, so there is no persistent market-data connection and thus none of the
one-websocket-per-subscription contention that per-instance streaming would hit.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Freshness window for a cached quote. The producer refreshes candidates well
# inside this, so a symbol that stays a candidate never ages out; one that leaves
# the candidate set drops from the published payload after this long (the TUI then
# shows "조회 중" rather than a stale price).
DEFAULT_TTL_SEC = 10.0

# Upper bound on how many symbols we keep warm, so a busy decision history can't
# grow the per-tick fetch without limit. Priority order (held > orders > recent)
# decides who survives the cap.
DEFAULT_CANDIDATE_CAP = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuoteBook:
    """In-memory ``symbol -> (price | error, fetched_at)`` cache with a TTL.

    Mirrors the ``_price_book`` pattern already used for resting-order prices, but
    is a standalone unit so it can be tested without a broker and reused as the
    single source for ``quotes.json``. A successful fetch stores a price; a failed
    fetch stores an error marker (so the panel can say "시세 없음" rather than the
    ambiguous "조회 중" it shows for a symbol that was never fetched at all).
    """

    def __init__(self, ttl_sec: float = DEFAULT_TTL_SEC) -> None:
        self._ttl = ttl_sec
        # symbol -> (price, fetched_at)
        self._prices: dict[str, tuple[float, datetime]] = {}
        # symbol -> (reason, fetched_at)
        self._errors: dict[str, tuple[str, datetime]] = {}

    def put(self, symbol: str, price: float, ts: datetime | None = None) -> None:
        sym = symbol.upper()
        self._prices[sym] = (float(price), ts or _utcnow())
        self._errors.pop(sym, None)

    def put_error(self, symbol: str, reason: str, ts: datetime | None = None) -> None:
        sym = symbol.upper()
        self._errors[sym] = (reason, ts or _utcnow())
        self._prices.pop(sym, None)

    def _fresh(self, ts: datetime, now: datetime) -> bool:
        return (now - ts).total_seconds() <= self._ttl

    def get(self, symbol: str, now: datetime | None = None) -> float | None:
        """Fresh cached price for *symbol*, or ``None`` if missing/stale/errored."""
        now = now or _utcnow()
        entry = self._prices.get(symbol.upper())
        if not entry:
            return None
        price, fetched_at = entry
        return price if self._fresh(fetched_at, now) else None

    def as_payload(self, now: datetime | None = None) -> dict:
        """Build the ``quotes.json`` body — only entries still within the TTL.

        Shape: ``{"quotes": {SYM: {"price": float, "ts": iso} | {"error": str,
        "ts": iso}}, "ttl_seconds": float}``. The caller stamps ``updated`` and
        ``provider``.
        """
        now = now or _utcnow()
        quotes: dict[str, dict] = {}
        for sym, (price, fetched_at) in self._prices.items():
            if self._fresh(fetched_at, now):
                quotes[sym] = {"price": price, "ts": fetched_at.isoformat()}
        for sym, (reason, fetched_at) in self._errors.items():
            if self._fresh(fetched_at, now):
                quotes[sym] = {"error": reason, "ts": fetched_at.isoformat()}
        return {"quotes": quotes, "ttl_seconds": self._ttl}


def quote_candidates(
    held: object,
    order_syms: object,
    recent_syms: object,
    cap: int = DEFAULT_CANDIDATE_CAP,
) -> list[str]:
    """Distinct, upper-cased click-candidate symbols in priority order.

    Held positions first (most likely clicked and always worth a fresh mark),
    then resting-order symbols, then recently decided/intervened symbols. Deduped
    preserving first occurrence and truncated to *cap*. Falsy / placeholder
    ("?") entries are dropped.
    """
    out: list[str] = []
    seen: set[str] = set()
    for group in (held, order_syms, recent_syms):
        for raw in group or ():
            if not raw or raw == "?":
                continue
            sym = str(raw).upper()
            if sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
            if len(out) >= cap:
                return out
    return out
