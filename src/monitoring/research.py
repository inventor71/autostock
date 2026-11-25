"""Read-only summary of the last injected research context, separate from process health."""
from __future__ import annotations

import json
from pathlib import Path


def read_context_summary(root) -> dict:
    try:
        record = json.loads((Path(root) / "research-context.json").read_text(encoding="utf-8"))
        news = record.get("news") or {}
        market = record.get("market_data") or {}
        news_gaps = {s: r["status"] for s, r in news.items() if r["status"] != "ok"}
        price_gaps = {s: r["quote"]["status"] for s, r in market.items() if r["quote"]["status"] != "ok"}
        bar_gaps = {s: r["bars"]["status"] for s, r in market.items() if r["bars"]["status"] != "ok"}
        unknown = [s for s, r in market.items() if r["quote"].get("source_age_seconds") is None]
        stale = [s for s, r in market.items() if r["quote"].get("source_age_seconds") is not None
                 and (r["quote"]["source_age_seconds"] > 60 or r["quote"]["source_age_seconds"] < -5)]
        degraded = news_gaps or price_gaps or bar_gaps or unknown or stale or record.get("account_error") or record.get("watchlist_not_refreshed")
        return {"status": "degraded" if degraded else "ok", "as_of": record["as_of"],
                "scope": "last intraday context, not process health",
                "news_gaps": news_gaps, "price_gaps": price_gaps, "bar_gaps": bar_gaps,
                "quote_time_unknown": unknown, "quote_older_than_60s_or_future": stale,
                "watchlist_not_refreshed": record.get("watchlist_not_refreshed", []),
                "account_error": record.get("account_error")}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "not_recorded", "as_of": None, "scope": "last intraday context"}

