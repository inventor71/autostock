"""HoldingsProvider protocol + type→builder registry (F81, FR-1).

A provider is the *only* place a specific disclosure format lives. To add a new
source, implement ``fetch_snapshot`` and register a builder in ``_BUILDERS`` —
nothing else in the holdings package changes.

``fetch_snapshot`` is the impure boundary (it does the HTTP). It is called ONLY by
the daemon refresher (``refresher.py``), never on the research-turn hot path.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from loguru import logger

from src.signals.holdings.records import HoldingsSnapshot


@runtime_checkable
class HoldingsProvider(Protocol):
    source_id: str
    manager_name: str

    def fetch_snapshot(self) -> HoldingsSnapshot:
        """Fetch + normalize this manager's latest disclosed holdings (impure)."""
        ...


# A builder turns one config entry (``{type, ...}``) + Settings into a provider,
# or None if it can't be built (missing/invalid config) — fail-honest, the
# refresher just skips a None.
ProviderBuilder = Callable[[dict, object], "HoldingsProvider | None"]


def _build_sec_13f(entry: dict, settings: object) -> "HoldingsProvider | None":
    # Imported lazily so the EDGAR-specific module (and its parsing deps) only
    # loads when an sec_13f provider is actually configured.
    from src.signals.holdings.providers.sec_13f import build_sec_13f_provider

    return build_sec_13f_provider(entry, settings)


# type tag → builder. New disclosure sources register here (one line).
_BUILDERS: dict[str, ProviderBuilder] = {
    "sec_13f": _build_sec_13f,
}


def build_providers(entries: list[dict], settings: object) -> list[HoldingsProvider]:
    """Build every configured provider, fail-honest per entry.

    An entry with an unknown ``type`` or a builder that returns None/raises is
    logged and skipped — one bad provider never blocks the others or the daemon.
    """
    providers: list[HoldingsProvider] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            logger.warning("holdings: ignoring non-dict provider entry: {!r}", entry)
            continue
        ptype = entry.get("type")
        builder = _BUILDERS.get(ptype)
        if builder is None:
            logger.warning("holdings: unknown provider type {!r}; skipping", ptype)
            continue
        try:
            provider = builder(entry, settings)
        except Exception as exc:  # noqa: BLE001 — one bad provider must not sink the rest
            logger.warning("holdings: provider {!r} failed to build: {}", ptype, exc)
            continue
        if provider is not None:
            providers.append(provider)
    return providers
