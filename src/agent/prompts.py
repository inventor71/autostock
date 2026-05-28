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

Ground every call in fresh data pulled THIS turn — do not reuse an RSI, level,
or price you only remember from the journal; re-pull it with the tools. Do the
following:

1. Account truth: run `python -m src.agent.tools account` to see real equity,
   cash, each holding's live price/P&L, and the orders actually resting at the
   broker (protective stop/target legs and pending entries). Reconcile it with
   your thesis files before deciding anything — a fill or a triggered stop may
   have changed the book since you last wrote it down.
2. Regime: refresh regime.md — SPY/QQQ/VIX, sector posture, macro — using the
   tools and web research.
3. Held positions — for EACH name in [{held_str}], this turn, mandatory:
   - `python -m src.agent.tools indicators <SYMBOL>` — fresh RSI/MACD/Bollinger/
     ATR; any stop or target you set must be grounded in the CURRENT ATR, not a
     recalled number.
   - `python -m src.agent.tools news <SYMBOL>` — scan for a thesis-breaking
     catalyst; a HOLD is only justified once you have checked the name's news.
   Then update positions/<SYMBOL>.md (thesis + plan + Call-vs-Outcome) and
   append the decision (HOLD carrying the stop/target you want enforced, or
   SELL / ADJUST_STOP if the thesis shifted).
4. Discovery: scan `python -m src.agent.tools scoreboard`, then for each
   promising candidate dig in with indicators / fundamentals / news (and web
   search) before writing a thesis. Add a BUY — always with a stop, and a target
   where you have one — only on genuine conviction.
5. Update watchlist.md with the names you are tracking and why.

Keep decisions.jsonl consistent with what your thesis files say.

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


def eod_review_prompt(outcomes: list[str] | None = None) -> str:
    """End-of-day turn: grade calls against outcomes, distill lessons, write note.

    ``outcomes`` are authoritative per-decision snapshots (levels vs current
    price, holding and P&L, a status hint) assembled from the broker/data so the
    grading is grounded in facts rather than the agent's recollection.
    """
    lines = ["End-of-day review turn (continuing today's session)."]
    if outcomes:
        lines.append("## Your calls and their current state (from the broker/market):")
        lines.extend(f"- {o}" for o in outcomes)
    lines.append(
        "Cross-check with decisions.jsonl and your position theses. For each call, "
        "compare what you intended to what actually happened and append a "
        "Call-vs-Outcome line in positions/<SYMBOL>.md. Distill any generalizable "
        "lesson — premature stop (stopped out then recovered), gave back gains "
        "(held too long), ignored an invalidated thesis, missed setup that worked, "
        "sizing too large/small — into lessons.md (one concise bullet each; only "
        "real, transferable lessons). Then write a daily/<date>.md with a "
        "self-grade of today's calls."
    )
    lines.append(_ADVISOR_REMINDER)
    return "\n".join(lines)
