"""Resolve the active tradeable universe from settings (replaces trading.symbols).

``resolve_universe`` is the single entry point every call site uses: it honours an
explicit ``--symbols`` override, else builds the per-market provider (US S&P 100 /
KR KIS market-cap) and returns ``get_symbols()`` (base ∪ enabled themes).
"""

from __future__ import annotations

from collections.abc import Sequence


def resolve_universe(settings, *, override: Sequence[str] | None = None,
                     market: str | None = None) -> list[str]:
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
        from src.execution.brokers.kis_rest import KisRestClient
        from src.universe.kr_provider import KRUniverseProvider

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

    return provider.get_symbols()
