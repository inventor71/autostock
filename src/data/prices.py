"""Concurrent latest-price fetch helper (R2 C-3p).

Value-preserving speedup: this issues the **same** ``data_provider.get_latest_price``
calls the callers already make, just concurrently, so each symbol receives the
identical price it would have sequentially. Per-symbol failures are isolated
(one bad fetch never sinks the rest), mirroring the callers' existing
``except: continue`` / ``except: pass`` behavior. The mutation/aggregation that
consumes these prices stays on the calling thread.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

# Bounded so a large universe can't spawn an unbounded thread count against the
# shared HTTP client; the calls are I/O-bound so a small pool already overlaps
# the network latency that dominated the old sequential loop.
_MAX_FETCH_WORKERS = 8


def fetch_latest_prices(data_provider, symbols) -> dict[str, float | None]:
    """Fetch latest prices for ``symbols`` concurrently.

    Returns ``{symbol: price}`` for successful fetches and ``{symbol: None}`` for
    any that raised — the caller decides how to treat a miss (the sequential
    callers simply skipped failures). Order of ``symbols`` is irrelevant to the
    result dict; callers iterate their own symbol list.
    """
    symbols = list(symbols)
    if not symbols:
        return {}
    if len(symbols) == 1:
        # No thread needed; keep the exact single-call path.
        sym = symbols[0]
        try:
            return {sym: data_provider.get_latest_price(sym)}
        except Exception:
            return {sym: None}

    def _one(sym: str):
        try:
            return sym, data_provider.get_latest_price(sym)
        except Exception:
            return sym, None

    workers = min(_MAX_FETCH_WORKERS, len(symbols))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(_one, symbols))
