"""BrokeredFetcher — assemble the ``ctx`` snapshot a predicate sees (U3, FR-4).

The predicate runs with NO network (`--network=none`); all data it can reason over
must be brokered in by the daemon (the trusted control plane) ahead of time. This
component resolves each declared :class:`SourceRef` into a plain JSON-serializable
``ctx`` dict that the sandbox mounts read-only.

Two source kinds (critic#2 — websearch is a follow-up, not here):

* ``signal`` → an injected ``signal_resolver(name, params)`` callable. The daemon
  wires this to the real :class:`SignalCollector`; tests pass a fake. Decoupling via
  injection keeps this unit testable without providers/network.
* ``webfetch`` → an allow-listed http(s) GET. The host MUST be on the configured
  domain allow-list (SSRF guard); the body is size-capped.

**Fail-honest, never fail-silent**: a source that errors is recorded in ``ctx`` as
``{"_error": "..."}`` under its key, so the predicate can *see* that the datum is
missing and decide accordingly — rather than reading a stale/absent value as 0.
``build_ctx`` itself never raises for a source failure.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from loguru import logger

from src.agent.triggers.models import SourceRef

# Resolves a catalogue signal name (+params) into JSON-able data. Injected.
SignalResolver = Callable[[str, dict[str, Any]], Any]

_BODY_CAP = 32 * 1024  # webfetch body chars kept in ctx


class HttpGet(Protocol):
    def __call__(self, url: str) -> tuple[int, str]:  # (status_code, body)
        ...


def _host(url: str) -> str:
    return re.sub(r"^https?://", "", url).split("/", 1)[0].split(":", 1)[0].lower()


def _domain_allowed(host: str, allowlist: frozenset[str]) -> bool:
    # exact host or a subdomain of an allow-listed domain
    return any(host == d or host.endswith("." + d) for d in allowlist)


class BrokeredFetcher:
    def __init__(
        self,
        *,
        signal_resolver: SignalResolver | None = None,
        http_get: HttpGet | None = None,
        webfetch_allowlist: frozenset[str] | None = None,
    ):
        self._resolve_signal = signal_resolver
        self._http_get = http_get
        self._allowlist = webfetch_allowlist or frozenset()

    def build_ctx(self, sources: list[SourceRef], *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        ctx: dict[str, Any] = {
            "_meta": {
                "built_at": now.isoformat(),
                "sources": [s.ctx_key() for s in sources],
            }
        }
        for src in sources:
            key = src.ctx_key()
            try:
                ctx[key] = self._resolve(src)
            except Exception as exc:  # fail-honest: surface, never crash the build
                logger.warning("brokered fetch failed for {}: {}", key, exc)
                ctx[key] = {"_error": str(exc)}
        return ctx

    # ---- per-source resolution --------------------------------------------- #
    def _resolve(self, src: SourceRef) -> Any:
        if src.kind == "signal":
            if self._resolve_signal is None:
                return {"_error": "no signal resolver configured"}
            return self._resolve_signal(src.name or "", dict(src.params))
        if src.kind == "webfetch":
            return self._webfetch(src.url or "")
        return {"_error": f"unknown source kind {src.kind!r}"}

    def _webfetch(self, url: str) -> Any:
        host = _host(url)
        if not _domain_allowed(host, self._allowlist):
            return {"_error": f"domain not allow-listed: {host}"}
        if self._http_get is None:
            return {"_error": "no http client configured"}
        status, body = self._http_get(url)
        if len(body) > _BODY_CAP:
            body = body[:_BODY_CAP]
        return {"status": status, "body": body, "host": host}


def default_http_get(*, connect_timeout: float = 3.0, read_timeout: float = 8.0) -> HttpGet:
    """Build a conservative httpx-based GET (lazy import; daemon-side only)."""
    import httpx

    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=read_timeout)

    def _get(url: str) -> tuple[int, str]:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "autostock-triggers/1.0"})
            return resp.status_code, resp.text

    return _get
