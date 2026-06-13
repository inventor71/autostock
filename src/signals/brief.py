"""Market-signal brief assembly + rendering — pure (F61, FR-5).

Combines movers + read-through alerts + imminent earnings into one
``MarketSignalBrief``, and renders it as the compact text prepended to the
research prompt (push) — the same object also feeds the on-demand tools (pull).
"""

from __future__ import annotations

from datetime import datetime

from src.signals.records import (
    ImminentEarnings,
    MarketSignalBrief,
    Mover,
    ReadThroughAlert,
    SentimentOutlier,
)


def assemble_brief(
    movers: list[Mover],
    readthrough_alerts: list[ReadThroughAlert],
    imminent_earnings: list[ImminentEarnings],
    degraded_sources: list[str] | None = None,
    *,
    sentiment_outliers: list[SentimentOutlier] | None = None,
    as_of: datetime | None = None,
) -> MarketSignalBrief:
    """Pure: bundle the parts into a brief (no I/O, no clock unless ``as_of`` omitted)."""
    return MarketSignalBrief(
        as_of=as_of or datetime.now(),
        movers=movers,
        readthrough_alerts=readthrough_alerts,
        imminent_earnings=imminent_earnings,
        sentiment_outliers=list(sentiment_outliers or []),
        degraded_sources=list(degraded_sources or []),
    )


def _fmt_pct(v: float) -> str:
    return f"{v:+.1f}%"


def to_prompt_text(brief: MarketSignalBrief) -> str:
    """Render the brief as the block prepended to the research prompt.

    Returns "" when there is nothing actionable (and no degraded sources) so the
    caller can skip the prepend entirely.
    """
    if brief.is_empty() and not brief.degraded_sources:
        return ""

    lines: list[str] = ["## Market signal brief (auto-collected this turn)"]

    if brief.movers:
        lines.append("Biggest movers (universe + bellwethers):")
        for m in brief.movers:
            tag = "" if m.in_universe else " [watch-only]"
            vol = f", vol x{m.volume_ratio:.1f}" if m.volume_ratio is not None else ""
            lines.append(f"  - {m.symbol}{tag} {_fmt_pct(m.change_pct)}{vol}")

    if brief.readthrough_alerts:
        lines.append(
            "Read-through to check (a big move may drag related names — "
            "YOU judge if it actually applies):"
        )
        for a in brief.readthrough_alerts:
            cause = f" ({a.cause_hint})" if a.cause_hint else ""
            peers = ", ".join(a.affected_peers)
            lines.append(
                f"  - {a.trigger_symbol} {_fmt_pct(a.trigger_change_pct)}{cause} "
                f"→ {peers}"
            )

    if brief.imminent_earnings:
        lines.append("Imminent earnings (universe / held):")
        for e in brief.imminent_earnings:
            held = " [HELD]" if e.is_held else ""
            when = f" {e.when}" if e.when != "unknown" else ""
            peers = f" — read-through: {', '.join(e.peer_readthrough)}" if e.peer_readthrough else ""
            lines.append(
                f"  - {e.symbol}{held} {e.earnings_date.isoformat()}{when}{peers}"
            )

    if brief.sentiment_outliers:
        lines.append(
            "Retail sentiment (StockTwits self-labels, deviation vs each "
            "symbol's OWN baseline — the crowd rests bullish):"
        )
        for o in brief.sentiment_outliers:
            rz = f"z={o.ratio_z:+.1f}" if o.ratio_z is not None else "z=?"
            vz = f", msgs z={o.volume_z:+.1f}" if o.volume_z is not None else ""
            lines.append(
                f"  - {o.symbol} bull {o.bull_ratio:.0%} (usually "
                f"{o.baseline_ratio:.0%}, {rz}{vz}, n={o.tagged_n}) — "
                f"{o.direction} shift"
            )

    if brief.degraded_sources:
        lines.append(
            "(some sources unavailable this turn: "
            + ", ".join(brief.degraded_sources)
            + ")"
        )

    return "\n".join(lines)
