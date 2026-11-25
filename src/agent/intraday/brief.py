"""BriefAssembler — the structured intraday brief injected into every turn (FR-2).

Goal: stop the agent re-deriving the book each tick (re-pulling quotes, re-stating
the same table). Data sources are strictly partitioned (critic#3/#6):
  * market data (price / session H-L / volume) -> ``BarCache`` (cached, off-bus, C-7)
  * account / fills / locks / pending -> the in-proc ``last_snapshot`` ONLY
    (never the broker; held symbols come from snapshot positions, NOT
    ``orchestrator.held_symbols`` which calls the broker, critic#6)
  * human context (directives) -> SteeringState (FR-7 / critic#1: F4 injects this
    only into reconcile turns, so the brief must carry it for intraday/wake turns)
The renderer borrows the *shape* of ``review.outcome_lines`` but NOT its data path
(that function calls ``broker.get_position`` directly — forbidden here, NFR-2).
"""

from __future__ import annotations

from src.agent.intraday.bars import BarCache


def _pct(level: float, price: float) -> str:
    if not price:
        return "?"
    return f"{(level - price) / price * 100:+.1f}%"


class BriefAssembler:
    def __init__(self, bar_cache: BarCache, *, state=None, watch_store=None,
                 sentiment_lines_fn=None):
        self._bars = bar_cache
        self._state = state
        self._watch = watch_store
        # F77: optional (symbols) -> brief lines for retail-sentiment outliers
        # among held/watch names. Best-effort — failures yield no lines.
        self._sentiment_lines_fn = sentiment_lines_fn

    def build(self, *, snapshot: dict | None, news: dict | None = None, news_coverage=None,
              include_news: bool = True, extra_symbols=()) -> str:
        if not snapshot:
            # Fail-closed: no live snapshot yet -> account-less brief, never crash.
            return "INTRADAY BRIEF: (no live account snapshot yet)"

        positions: dict = snapshot.get("positions", {}) or {}
        opens = snapshot.get("open_orders", []) or []
        fills = snapshot.get("fills", []) or []
        locked = snapshot.get("locked_symbols", {}) or {}

        watch_by_sym: dict[str, list] = {}
        if self._watch is not None:
            try:
                for t in self._watch.active():
                    watch_by_sym.setdefault(t.symbol, []).append(t)
            except Exception:
                pass

        symbols = list(dict.fromkeys(
            [*positions.keys(), *watch_by_sym.keys(), *extra_symbols]
        ))

        lines = ["INTRADAY BRIEF"]
        lines.append("Price timestamps identify source data; retrieval time does not prove a live quote. "
                     "Bar ranges cover the returned window, not necessarily the whole session.")
        if snapshot.get("account_error") or snapshot.get("open_orders_error"):
            lines.append(f"ACCOUNT incomplete: {snapshot.get('account_error') or snapshot.get('open_orders_error')}")
        account = snapshot.get("account", snapshot)
        lines.append(f"ACCOUNT snapshot_at={snapshot.get('as_of') or snapshot.get('timestamp') or 'unknown'} "
                     f"equity={account.get('equity', 'unknown')} cash={account.get('cash', 'unknown')}")
        for sym in symbols:
            lines.append(self._symbol_line(sym, positions, opens, watch_by_sym, news))

        if self._sentiment_lines_fn is not None:
            try:
                lines.extend(self._sentiment_lines_fn(symbols))
            except Exception:
                pass  # sentiment is optional context — never blocks the brief

        lines.append(self._human_line(locked, snapshot))
        delta = self._delta_line(fills)
        if delta:
            lines.append(delta)
        if include_news and news:
            news_line = self._news_line(news)
            if news_line:
                lines.append(news_line)
        if include_news:
            coverage = news_coverage or {s: {"status": "not_checked"} for s in symbols}
            groups = {}
            for sym, row in coverage.items():
                groups.setdefault(row["status"], []).append(sym)
            lines.append("NEWS coverage: " + "; ".join(f"{k}=[{','.join(v)}]" for k, v in groups.items()))
            providers = sorted({r["provider"] for r in coverage.values() if r.get("provider")})
            fetched = [r["fetched_at"] for r in coverage.values() if r.get("fetched_at")]
            errors = sorted({e for r in coverage.values() for e in r.get("errors", [])})
            lines.append(f"NEWS providers={providers} oldest_fetch={min(fetched) if fetched else 'unknown'} "
                         f"fallback/errors={errors}. Coverage is limited to these feeds; "
                         "unavailable/stale/unchecked is unknown, not 'no catalyst'.")
        return "\n".join(lines)

    # ---- per-symbol -------------------------------------------------------- #
    def _symbol_line(self, sym, positions, opens, watch_by_sym, news) -> str:
        price = self._bars.get_price(sym)
        bars = self._bars.get_bars(sym)
        parts = [sym]
        if price is not None:
            parts.append(f"px={price:.2f}")
        metadata = self._bars.coverage(sym)
        q = metadata["quote"]
        parts.append(f"quote={q['status']} source={q.get('source_as_of') or 'unknown'} "
                     f"age_s={q.get('source_age_seconds')} fetch_age_s={q.get('fetch_age_seconds')}")
        if bars is not None and len(bars) > 0:
            try:
                parts.append(f"windowH/L={bars['high'].max():.2f}/{bars['low'].min():.2f}")
                parts.append(f"vol={float(bars['volume'].iloc[-1]):.0f}")
                parts.append(f"bars={metadata['bars']['timeframe']}@{metadata['bars']['source_as_of']} "
                             f"{metadata['bars']['status']}")
                first = float(bars["open"].iloc[0])
                if first and price:
                    parts.append(f"vs_window_open={(price / first - 1) * 100:+.2f}%")
            except Exception:
                pass
        else:
            parts.append("bars=unavailable")
        levels = []
        pos = positions.get(sym)
        if pos:
            qty = pos.get("qty")
            avg = pos.get("avg_entry_price")
            # F54: label SHORT so a cheap wake turn (which may not re-pull the
            # account tool) doesn't read a short as a long and misjudge direction.
            side = pos.get("side", "long")
            side_tag = "SHORT " if side == "short" else ""
            levels.append(f"{side_tag}qty={qty}@{avg}")
        for o in opens:
            if o.get("symbol") != sym:
                continue
            if o.get("stop_price"):
                levels.append(f"stop={o['stop_price']}"
                              + (f"({_pct(o['stop_price'], price)})" if price else ""))
            if o.get("limit_price"):
                levels.append(f"lmt={o['limit_price']}"
                              + (f"({_pct(o['limit_price'], price)})" if price else ""))
        for t in watch_by_sym.get(sym, []):
            tag = f"watch={t.condition} {t.level}"
            if price:
                tag += f"({_pct(t.level, price)})"
            levels.append(tag)
        if levels:
            parts.append("| " + " ".join(levels))
        return "  " + "  ".join(parts)

    # ---- human context (critic#1) ----------------------------------------- #
    def _human_line(self, locked, snapshot) -> str:
        directives = "none"
        if self._state is not None:
            try:
                directives = "; ".join(d.text for d in self._state.active_directives()) or "none"
            except Exception:
                directives = "none"
        pending = snapshot.get("pending", []) or []
        locked_syms = [s for s, st in locked.items() if st]
        return (f"HUMAN: directives=[{directives}] "
                f"pending_approvals={len(pending)} locked={locked_syms or 'none'}")

    # ---- delta / news ------------------------------------------------------ #
    def _delta_line(self, fills) -> str:
        if not fills:
            return ""
        bits = [f"{f.get('side')}{f.get('qty')} {f.get('symbol')}@{f.get('price')}"
                for f in fills]
        return "DELTA new_fills: " + "; ".join(bits)

    def _news_line(self, news) -> str:
        # news is dict[str, NewsDiff] from NewsPoller.diff_for.
        bits = []
        for sym, nd in news.items():
            heads = getattr(nd, "headlines", None)
            if heads:
                articles = getattr(nd, "articles", [])
                if articles:
                    rendered = [f"{a['title'][:240]} [published={a.get('published_at') or 'unknown'}; "
                                f"{a.get('link', '')}]" for a in articles[:2]]
                    bits.append(f"{sym}: " + "; ".join(rendered)
                                + (f" (+{len(articles) - 2} more; news tool for details)" if len(articles) > 2 else ""))
                else:
                    bits.append(f"{sym}: {heads[0]} [published=unknown]")
        return ("NEWS (new): " + " | ".join(bits)) if bits else ""
