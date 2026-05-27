"""Turn prompts for the PM agent's daily session.

Three turn types drive the daily session: a deep morning research turn, light
intraday update turns (resumed, cheap), and an end-of-day review turn. The
durable role/rules live in the workspace ``CLAUDE.md`` (auto-loaded as cwd);
these prompts only carry the turn-specific task and live context.
"""

from __future__ import annotations

from datetime import date

_ADVISOR_REMINDER = (
    "You are advisory only: never place, modify, or cancel orders. Record "
    "intended actions in decisions.jsonl per the schema in CLAUDE.md; the "
    "executor applies guardrails and trades. Market/broker access is read-only."
)


def morning_research_prompt(
    universe: list[str],
    held: list[str] | None = None,
    today: date | None = None,
) -> str:
    """Deep morning turn: regime, pure-LLM discovery, theses, decisions."""
    today = today or date.today()
    held_str = ", ".join(held) if held else "none"
    universe_str = ", ".join(universe)
    return f"""Morning research turn — {today.isoformat()}.

Start by reading CLAUDE.md, lessons.md, regime.md, watchlist.md, and the thesis
file for every held/tracked name.

Positions to manage: {held_str}.

Tradeable universe — you may ONLY act on these symbols (this is the menu;
choose what is worth deep work yourself, there is no pre-filtered shortlist):
{universe_str}

Do the following:
1. Refresh regime.md — SPY/QQQ/VIX, sector posture, macro — using the tools and
   web research.
2. Discover candidates: scan with `python -m src.agent.tools scoreboard`, then
   dig into the most promising names with quote / indicators / fundamentals /
   news and web search.
3. For each held position and each strong candidate, write or update
   positions/<SYMBOL>.md with a thesis + a plan (entry / stop / target) and a
   Call-vs-Outcome line.
4. Update watchlist.md with the names you are tracking and why.
5. Append actionable decisions to decisions.jsonl (BUY / SELL / HOLD /
   ADJUST_STOP), always with a stop for BUYs and a target where you have one.

{_ADVISOR_REMINDER}"""


def intraday_prompt(
    quotes: dict[str, float] | None = None,
    held: list[str] | None = None,
) -> str:
    """Light resumed turn: act only if a plan triggers or the thesis shifts."""
    held_str = ", ".join(held) if held else "none"
    lines = ["Intraday update turn (continuing today's session)."]
    if quotes:
        rendered = "; ".join(f"{sym}={price}" for sym, price in quotes.items())
        lines.append(f"Current prices: {rendered}.")
    lines.append(f"Positions / watchlist to check: {held_str}.")
    lines.append(
        "Re-check your existing plans: has price reached a planned entry, stop, "
        "or target, or has the thesis changed (fresh news/catalyst)? If so, "
        "update the relevant positions/<SYMBOL>.md and append the decision "
        "(including ADJUST_STOP to tighten a stop) to decisions.jsonl. If nothing "
        "is triggered, do nothing — do not churn."
    )
    lines.append(_ADVISOR_REMINDER)
    return "\n".join(lines)


def eod_review_prompt(decisions_today: list[str] | None = None) -> str:
    """End-of-day turn: grade calls, distill lessons, write the daily note."""
    lines = ["End-of-day review turn (continuing today's session)."]
    if decisions_today:
        lines.append("Decisions on record (recent): " + "; ".join(decisions_today) + ".")
    lines.append(
        "Read decisions.jsonl and your position theses. For each, compare the "
        "call to what actually happened today and append a Call-vs-Outcome line "
        "in positions/<SYMBOL>.md. Distill any generalizable lesson — premature "
        "stop, gave back gains, ignored an invalidated thesis, missed setup, "
        "sizing too large/small — into lessons.md (one bullet each). Then write a "
        "concise daily/<date>.md with a self-grade of today's calls."
    )
    lines.append(_ADVISOR_REMINDER)
    return "\n".join(lines)
