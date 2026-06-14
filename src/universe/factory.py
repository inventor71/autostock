"""Resolve the active tradeable universe from settings (replaces trading.symbols).

``resolve_universe`` is the single entry point every call site uses: it honours an
explicit ``--symbols`` override, else builds the per-market provider (US S&P 100 /
KR KIS market-cap) and returns ``get_symbols()`` (base ∪ enabled themes), then
unions the disclosed-holdings overlay (F81 — institutional 13F long/short names).
"""

from __future__ import annotations

from collections.abc import Sequence

from loguru import logger


def resolve_universe(settings, *, override: Sequence[str] | None = None,
                     market: str | None = None, client=None) -> list[str]:
    ucfg = getattr(settings, "universe", None) or {}
    override = override or ucfg.get("override")  # --symbols (set in main)
    if override:
        return list(dict.fromkeys(s.strip().upper() for s in override if s.strip()))

    from config.config import CONFIG_DIR

    market = (market or ucfg.get("market") or "us").lower()
    themes = (ucfg.get("themes") or {}).get(market) or {}
    enabled = ucfg.get("enabled_themes") or []
    snap_dir = CONFIG_DIR / "universe"

    if market == "kr":
        from src.universe.kr_provider import KRUniverseProvider

        if client is None:
            # No shared broker client (e.g. backtest): make one. In the live agent
            # path main passes broker.client so both honour the 1-token/min cap.
            from src.execution.brokers.kis.rest import KisRestClient
            client = KisRestClient(
                settings.kis_paper_api_key, settings.kis_paper_api_secret, paper=True)
        provider = KRUniverseProvider(
            client, snapshot_path=snap_dir / "kr_base.json",
            themes=themes, enabled_themes=enabled)
    else:
        from src.universe.us_provider import USUniverseProvider

        provider = USUniverseProvider(
            snapshot_path=snap_dir / "us_base.json",
            top_n=int(ucfg.get("top_n", 100)), themes=themes, enabled_themes=enabled)

    symbols = provider.get_symbols()
    overlay = _holdings_overlay(settings)
    if overlay:
        symbols = sorted(set(symbols) | set(overlay))  # union-only, never removes
    return symbols


def _holdings_overlay(settings) -> list[str]:
    """F81 disclosed-holdings universe overlay — fail-honest (never blocks resolve).

    Reads the cached 13F snapshots the daemon refresher wrote and returns the long
    (and, when ``risk.shorting_enabled``, short) tickers of overlay-enabled sources.
    Any error → no overlay, so the base universe is always usable.
    """
    try:
        from src.signals.holdings.overlay import holdings_universe_overlay
        from src.signals.holdings.provider import build_providers
        from src.signals.holdings.store import read_snapshots
        from src.signals.settings import SignalsConfig

        cfg = SignalsConfig.from_settings(getattr(settings, "signals", None)).disclosed_holdings
        if not cfg.enabled:
            return []
        providers = build_providers(cfg.providers, settings)
        overlay_ids = {p.source_id for p in providers if getattr(p, "overlay", False)}
        if not overlay_ids:
            return []
        shorting = bool(getattr(getattr(settings, "risk", None), "shorting_enabled", False))
        return holdings_universe_overlay(
            read_snapshots(), overlay_ids,
            shorting_enabled=shorting, max_age_days=cfg.max_age_days,
        )
    except Exception as exc:  # noqa: BLE001 — overlay is additive; never fail the universe
        logger.warning("universe: disclosed-holdings overlay skipped ({})", exc)
        return []
