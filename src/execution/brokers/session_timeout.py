"""Inject a default ``(connect, read)`` timeout into an alpaca-py client's session.

alpaca-py 0.43.2 exposes no timeout parameter on ``TradingClient`` /
``StockHistoricalDataClient`` / ``RESTClient``, and its internal ``_request`` does
not pass one — so a half-open socket blocks **forever** (no exception). That
silently wedges the single CommandBus worker and the scheduler threads (the F14
wedge): with no exception, the best-effort ``try/except`` around broker/data calls
never fires, so nothing self-heals.

Fix: wrap the client's underlying ``requests.Session.request`` so any call that
does not already specify ``timeout`` gets ``(connect, read)``. A timeout then
raises ``requests.exceptions.Timeout``, which the existing best-effort handlers
catch and retry on the next tick.

Idempotent (marked) so re-applying the same helper to a shared/re-created client
never double-wraps (stacked wrappers would be harmless but confusing). Best-effort:
if a future SDK changes the session shape, log and no-op rather than breaking
client construction (SECURITY-15 fail-safe — but note timeout is then NOT applied;
worktree live-verify confirms it actually takes effect on the pinned SDK).
"""

from __future__ import annotations

from loguru import logger

#: marker set on the wrapped ``request`` callable so re-application is a no-op.
_WRAPPED_MARK = "__autostock_timeout_wrapped__"


def install_session_timeout(client, *, connect: float = 3.0, read: float = 5.0) -> None:
    """Best-effort: force a default ``(connect, read)`` timeout on ``client``'s session."""
    session = getattr(client, "_session", None)
    request = getattr(session, "request", None)
    if request is None:
        logger.warning(
            "install_session_timeout: {} has no requests.Session (_session.request); "
            "HTTP timeout NOT applied",
            type(client).__name__,
        )
        return
    if getattr(request, _WRAPPED_MARK, False):
        return  # already wrapped — idempotent (shared/re-created client)
    timeout = (connect, read)

    def _request_with_timeout(*args, **kwargs):
        kwargs.setdefault("timeout", timeout)  # caller-supplied timeout is honored
        return request(*args, **kwargs)

    setattr(_request_with_timeout, _WRAPPED_MARK, True)
    session.request = _request_with_timeout
