"""Turn prompts for the PM agent's daily session.

Three turn types drive the daily session: a deep morning research turn, light
intraday update turns (resumed, cheap), and an end-of-day review turn. The
durable role/rules live in the workspace ``CLAUDE.md`` (auto-loaded as cwd);
these prompts only carry the turn-specific task and live context.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.journal import LessonRecord

_ADVISOR_REMINDER = (
    "You are advisory only: never place, modify, or cancel orders. Record "
    "intended actions in decisions.jsonl per the schema in CLAUDE.md; the "
    "executor applies guardrails and trades. Market/broker access is read-only."
)


def morning_research_prompt(
    universe: list[str],
    held: list[str] | None = None,
    today: date | None = None,
    shorting_enabled: bool = True,
    signal_brief: str | None = None,
) -> str:
    """Deep morning turn: regime, pure-LLM discovery, theses, decisions.

    ``shorting_enabled`` gates the short-selling guidance: when shorts are off
    (the shipped default), the agent isn't told to find shorts — so it doesn't
    waste turns proposing SELL_SHORTs the executor would reject.

    F61: when a Python-assembled ``signal_brief`` is supplied (movers,
    read-through, imminent earnings), it is prepended so the agent sees what just
    moved in the market before it starts. None → unchanged (backward compatible).
    """
    today = today or date.today()
    held_str = ", ".join(held) if held else "none"
    universe_str = ", ".join(universe)
    prefix = f"{signal_brief}\n\n" if signal_brief else ""
    short_discovery = (
        " Equally, consider SHORT candidates (overvalued / broken / "
        "negative-catalyst names): run `short_data` first and add a SELL_SHORT "
        "(stop above entry, mandatory) on genuine conviction."
        if shorting_enabled else ""
    )
    short_block = f"\n{_SHORT_GUIDANCE}\n" if shorting_enabled else ""
    return f"""{prefix}Morning research turn — {today.isoformat()}.
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
   where you have one — only on genuine conviction.{short_discovery}
5. Update watchlist.md with the names you are tracking and why.
{short_block}
Keep decisions.jsonl consistent with what your thesis files say.

{_ADVISOR_REMINDER}"""


def intraday_prompt(
    quotes: dict[str, float] | None = None,
    held: list[str] | None = None,
    brief: str | None = None,
) -> str:
    """Light resumed turn: act only if a plan triggers or the thesis shifts.

    F3: when a Python-assembled ``brief`` is supplied (price/levels/distance,
    account truth, human context, delta, news), it replaces the bare quotes/held
    lines so the agent reasons over a ready book instead of re-deriving it."""
    lines = ["Intraday update turn (continuing today's session)."]
    if brief:
        lines.append(brief)
    else:
        held_str = ", ".join(held) if held else "none"
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


def wake_prompt(brief: str | None, reasons: list[str] | None = None) -> str:
    """Event-driven wake turn (F3 FR-4): Python detected judgement-worthy events
    out-of-band (a fill, an abnormal move, a met watch condition, a protective
    fill) and woke the agent before the next scheduled tick. Scoped to the
    events — not a full re-survey."""
    lines = ["Event-driven wake turn (continuing today's session) — Python "
             "detected judgement-worthy events out-of-band."]
    if reasons:
        lines.append("Trigger(s):")
        lines.extend(f"  - {r}" for r in reasons)
    if brief:
        lines.append(brief)
    lines.append(
        "Assess ONLY what these events imply for your existing plans: confirm a "
        "fill against your journal, reassess a thesis on an abnormal move, judge "
        "whether a met watch condition warrants an ADJUST_STOP, or handle a "
        "protective fill. Append any decision (incl. ADJUST_STOP) to "
        "decisions.jsonl. If the events need no action, do nothing — do not churn."
    )
    lines.append(
        "TIME CONSTRAINT — this is a short, out-of-band wake turn. Check ONLY the "
        "specific symbol(s) named in the trigger(s) above. Do NOT re-read every "
        "thesis file or do a full portfolio review. If you need more depth, defer "
        "it to the next scheduled intraday turn."
    )
    lines.append(_ADVISOR_REMINDER)
    return "\n".join(lines)


# -- F23: multi-agent research prompts ------------------------------------ #

_SIGNAL_TOOL_GUIDE = {
    "quote": "`python -m src.agent.tools quote <SYM>` — latest price, OHLCV, % changes",
    "indicators": "`python -m src.agent.tools indicators <SYM>` — RSI, MACD, Bollinger, SMA, ATR",
    "fundamentals": "`python -m src.agent.tools fundamentals <SYM>` — P/E, margins, growth, short interest, analyst target",
    "news": "`python -m src.agent.tools news <SYM>` — recent headlines with sentiment",
    "scoreboard": "`python -m src.agent.tools scoreboard` — compact universe scan",
    "earnings": "`python -m src.agent.tools earnings <SYM>` — next earnings date, consensus EPS, surprise history",
    "insider": "`python -m src.agent.tools insider <SYM>` — insider buy/sell from SEC Form 4",
    "macro": "`python -m src.agent.tools macro` — Treasury yields, Dollar, Gold, Oil, VIX",
    "analyst_upgrades": "`python -m src.agent.tools analyst_upgrades <SYM>` — recent upgrade/downgrade actions",
    "institutional": "`python -m src.agent.tools institutional <SYM>` — top institutional holders",
    "account": "`python -m src.agent.tools account` — live equity, positions, resting orders",
    "short_data": "`python -m src.agent.tools short_data <SYM>` — short interest, days-to-cover, squeeze_risk flag (check before any short)",
    "movers": "`python -m src.agent.tools movers` — today's biggest movers (universe + bellwethers) with read-through alerts",
    "readthrough": "`python -m src.agent.tools readthrough <SYM>` — peer names a big move in SYM may read through to",
    "earnings_calendar": "`python -m src.agent.tools earnings_calendar` — imminent earnings (universe / held) within the horizon",
}


# F54: shared short-selling guidance injected into entry-decision turns. The
# market can fall as well as rise; a balanced book may carry shorts. The agent
# is still advisory-only — it writes SELL_SHORT/BUY_TO_COVER decisions, the
# executor + RiskManager apply the (mandatory-stop, squeeze) guardrails.
_SHORT_GUIDANCE = """## Short selling (when the setup favors the downside)
Do not stay long-only in a weak tape. You may SHORT a name that is overvalued,
technically broken, or carrying a fresh negative catalyst — just as rigorously
as a long:
- Before shorting, run `short_data <SYM>`. If squeeze_risk is HIGH/ELEVATED
  (high short float / low days-to-cover), size down or skip — squeezes are how
  shorts blow up.
- A short MUST carry a stop ABOVE entry (a short's loss is unbounded). A
  SELL_SHORT decision with no stop is REJECTED by the executor. Set `target`
  BELOW entry.
- Only easy-to-borrow names can be shorted: the executor rejects a SELL_SHORT on
  a non-easy-to-borrow / non-shortable symbol (skipped_not_shortable). Prefer
  liquid large-caps; don't waste a decision shorting an illiquid name.
- Actions: SELL_SHORT to open a short, BUY_TO_COVER to close it. To reverse an
  existing long into a short, just emit SELL_SHORT — the executor closes the
  long first, then opens the short (no separate SELL needed)."""

_VERDICT_SCHEMA = """## Verdict
For each symbol you have a view on, write one block:
- symbol: <TICKER>
- action: BUY | SELL | HOLD | ADJUST_STOP | SELL_SHORT | BUY_TO_COVER
- confidence: 0.0-1.0
- stop: <price or null>   (REQUIRED for SELL_SHORT — above entry; for BUY it's below)
- target: <price or null> (for SELL_SHORT, below entry)
- reason: <one-line rationale>"""


def _build_signal_guide(signals: list[str] | None = None) -> str:
    if not signals:
        signals = list(_SIGNAL_TOOL_GUIDE.keys())
    lines = ["Available analysis tools:"]
    seen = set()
    for sig in signals:
        if sig in _SIGNAL_TOOL_GUIDE and sig not in seen:
            lines.append(f"  - {_SIGNAL_TOOL_GUIDE[sig]}")
            seen.add(sig)
    if "account" not in seen:
        lines.append(f"  - {_SIGNAL_TOOL_GUIDE['account']}")
    return "\n".join(lines)


def _build_lesson_context(lessons: "list[LessonRecord]", max_n: int = 10) -> str:
    if not lessons:
        return ""
    recent = lessons[-max_n:]
    lines = ["\n## Recent lessons from past trades (apply these):"]
    for r in recent:
        lines.append(f"- [{r.date}] [{r.category}] {r.takeaway}")
    return "\n".join(lines)


def multi_research_initial_prompt(
    universe: list[str],
    held: list[str] | None = None,
    signals: list[str] | None = None,
    lessons: "list[LessonRecord] | None" = None,
    n_rounds: int = 2,
    max_lessons: int = 10,
    today: date | None = None,
shorting_enabled: bool = True,
signal_brief: str | None = None,) -> str:
    today = today or date.today()
    held_str = ", ".join(held) if held else "none"
    universe_str = ", ".join(universe)
    lesson_ctx = _build_lesson_context(lessons or [], max_n=max_lessons)
    signal_guide = _build_signal_guide(signals)
    discovery = (
        "4. Discovery: scan scoreboard, dig into promising candidates — long AND "
        "short\n   (run short_data before any short; squeeze_risk HIGH/ELEVATED → "
        "size down/skip)."
        if shorting_enabled else
        "4. Discovery: scan scoreboard, dig into promising long candidates."
    )
    short_block = f"\n{_SHORT_GUIDANCE}\n" if shorting_enabled else ""
    prefix = f"{signal_brief}\n\n" if signal_brief else ""  # F61 market-signal brief
    return f"""{prefix}Morning research turn — {today.isoformat()} (multi-agent, round 1 of {n_rounds + 1}).

Start by reading CLAUDE.md, lessons.md, regime.md, watchlist.md, and the thesis
file for every held/tracked name.

Positions to manage: {held_str}.
Tradeable universe: {universe_str}

{signal_guide}
{lesson_ctx}

Ground every call in fresh data pulled THIS turn. Do the following:
1. Account truth: run `python -m src.agent.tools account`
2. Regime: refresh regime.md using tools and web research.
3. Held positions: for EACH held name, pull indicators + news, update thesis.
{discovery}
5. Update watchlist.md.
{short_block}
This is round 1 of a {n_rounds + 1}-round cross-validation process.
Do NOT write to decisions.jsonl yet — record your analysis and preliminary
views in your session context. The last round will produce the verdicts.

{_ADVISOR_REMINDER}"""


def debate_prompt(round_num: int, total_rounds: int) -> str:
    return f"""Cross-validation round {round_num + 1} of {total_rounds + 1}.

Critically evaluate your previous analysis:
- Are there risks or opportunities you missed?
- Is your data interpretation biased (confirmation bias, recency bias)?
- Does your regime assessment match current conditions?
- Would a contrarian view be more defensible for any position?

Challenge your own conclusions. Pull additional data with tools if needed.
Do NOT write to decisions.jsonl — this is an evaluation round.

{_ADVISOR_REMINDER}"""


def synthesis_prompt(total_rounds: int) -> str:
    return f"""Final synthesis round (round {total_rounds + 1} of {total_rounds + 1}).

You have completed {total_rounds} rounds of analysis and cross-validation.
Now produce your final verdicts:

1. For each symbol, weigh all bull and bear arguments from previous rounds.
2. Record final decisions in decisions.jsonl (BUY/SELL/HOLD/ADJUST_STOP with
   stop, target, confidence, and reason).
3. Write a structured verdict summary:

{_VERDICT_SCHEMA}

Only record decisions you have genuine conviction about after the full
cross-validation. Quality over quantity.

{_ADVISOR_REMINDER}"""


def sub_agent_prompt(
    task_description: str,
    universe: list[str],
    signals: list[str] | None = None,
    today: date | None = None,
) -> str:
    today = today or date.today()
    universe_str = ", ".join(universe)
    signal_guide = _build_signal_guide(signals)
    return f"""You are an independent analyst for a PM trading agent — {today.isoformat()}.

Your assigned task: {task_description}

Tradeable universe: {universe_str}

{signal_guide}

Produce a thorough analysis. At the end, include a structured verdict:

{_VERDICT_SCHEMA}

Do NOT write to decisions.jsonl — the Manager will make the final decisions.
Your output (this response) is your full report.

{_ADVISOR_REMINDER}"""


def parallel_synthesis_prompt(reports: list[str]) -> str:
    sections = []
    for i, report in enumerate(reports):
        sections.append(f"--- Analyst {i + 1} Report ---\n{report}\n")
    reports_text = "\n".join(sections)
    return f"""You have received reports from {len(reports)} independent analysts:

{reports_text}

Cross-validate their findings:
1. Where analysts agree, confidence is higher.
2. Where they disagree, pull additional data to resolve.
3. Produce final decisions in decisions.jsonl.
4. Write a structured verdict summary:

{_VERDICT_SCHEMA}

{_ADVISOR_REMINDER}"""


def eod_review_prompt(
    outcomes: list[str] | None = None,
    quality_summary: str | None = None,
    surge_count: int = 0,
) -> str:
    """End-of-day turn: grade calls against outcomes, distill lessons, write note.

    ``outcomes`` are authoritative per-decision snapshots (levels vs current
    price, holding and P&L, a status hint) assembled from the broker/data so the
    grading is grounded in facts rather than the agent's recollection.

    ``quality_summary`` is an optional compact digest of decision quality metrics
    (direction hit rate, MAE/MFE, stop quality, confidence calibration) injected
    when enough data exists (>= 5 decisions).

    ``surge_count`` is the number of surge/dive stocks detected today (F47).
    When > 0 the agent is instructed to analyse each one.
    """
    lines = ["End-of-day review turn (continuing today's session)."]
    if outcomes:
        lines.append("## Your calls and their current state (from the broker/market):")
        lines.extend(f"- {o}" for o in outcomes)
    if quality_summary is not None:
        lines.append("## Decision Quality Metrics (statistical, from your track record):")
        lines.append(quality_summary)
    if surge_count > 0:
        lines.append("## Today's Surge / Dive Stocks")
        lines.append(
            f"{surge_count} stock(s) surged or dived beyond the threshold today. "
            "Run `python -m src.agent.tools surge-list` to see them."
        )
        lines.append(
            "For EACH surge/dive stock, run "
            "`python -m src.agent.tools surge-analyze <SYMBOL> <DATE> <CAUSE> "
            "\"<LEADING_INDICATORS>\" \"<INFORMATION_GAP>\"` where:"
        )
        lines.append(
            "- CAUSE: earnings | news | sector | technical | after_hours | mna | macro | unknown"
        )
        lines.append(
            "- LEADING_INDICATORS: What signals preceded this move "
            "that autostock could have detected?"
        )
        lines.append(
            "- INFORMATION_GAP: What data would have helped predict this, "
            "that autostock doesn't currently capture?"
        )
        lines.append(
            "After analysing, write a daily surge summary to surge/YYYY-MM-DD.md "
            "with key takeaways and recurring information gaps."
        )
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
