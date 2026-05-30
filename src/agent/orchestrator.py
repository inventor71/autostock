"""Slow-loop orchestrator: drives the PM agent's daily session.

This is the agentic path's own loop — deliberately NOT a ``BaseStrategy`` on
``TradingEngine`` (that engine is per-symbol; the PM reasons over the whole book
in one turn). It sequences the daily turn types (morning research / intraday /
EOD review), supplies live context (universe menu, held positions), and tracks
which decisions each turn produced. It writes only to the journal; reading
``decisions.jsonl`` and executing via RiskManager/Broker is the DecisionExecutor's
job (see ``src/agent/executor.py``).
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.agent import prompts
from src.agent.journal import Decision, Journal
from src.agent.session import AgentSession, AgentTurnResult
from src.core.models import PortfolioState


def filter_in_universe(
    decisions: list[Decision], universe: list[str]
) -> tuple[list[Decision], list[Decision]]:
    """Split decisions into (in-universe, rejected) by the tradeable pool."""
    pool = {s.upper() for s in universe}
    kept = [d for d in decisions if d.symbol in pool]
    rejected = [d for d in decisions if d.symbol not in pool]
    return kept, rejected


class AgentTradingLoop:
    """Sequences the daily agent turns and enforces the pool constraint."""

    def __init__(
        self,
        session: AgentSession | None = None,
        *,
        universe: list[str],
        portfolio_provider: Callable[[], PortfolioState] | None = None,
        research_model: str | None = None,
        research_timeout: float | None = None,
    ):
        self.session = session or AgentSession()
        self.journal: Journal = self.session.journal
        self.universe = universe
        # Deeper model + longer timeout for the daily research turn; None = session default.
        self.research_model = research_model
        self.research_timeout = research_timeout
        # Optional source of real holdings (a broker); falls back to the journal's
        # tracked theses when no broker is supplied.
        self.portfolio_provider = portfolio_provider

        # Populated after each turn for inspection and the executor handoff.
        self.last_new_decisions: list[Decision] = []
        self.last_kept: list[Decision] = []
        self.last_rejected: list[Decision] = []

    # ------------------------------------------------------------------ #
    def held_symbols(self) -> list[str]:
        """Symbols currently held, from the live broker if wired, else the
        journal's tracked theses (the offline fallback)."""
        if self.portfolio_provider is not None:
            try:
                return sorted(self.portfolio_provider().positions.keys())
            except Exception as exc:
                logger.warning(f"portfolio_provider failed, using journal: {exc}")
        return self.journal.list_positions()

    def _run(
        self, prompt: str, turn_type: str, model: str | None = None, timeout: float | None = None
    ) -> AgentTurnResult:
        before = len(self.journal.read_decisions())
        result = self.session.run_turn(prompt, model=model, timeout=timeout)
        self.last_new_decisions = self.journal.read_decisions()[before:]
        self.last_kept, self.last_rejected = filter_in_universe(
            self.last_new_decisions, self.universe
        )
        for d in self.last_rejected:
            logger.warning(
                f"Out-of-universe decision will be rejected at execution: "
                f"{d.symbol} {d.action}"
            )
        logger.info(
            "Turn produced {} decision(s); {} in-universe, {} rejected",
            len(self.last_new_decisions), len(self.last_kept), len(self.last_rejected),
        )
        # Capture the turn's cost/activity (ephemeral CLI telemetry).
        from src.agent.turn_log import record_turn
        record_turn(
            self.journal.root / "turns.jsonl",
            turn_type=turn_type,
            model=model or getattr(self.session, "model", "unknown"),
            num_decisions=len(self.last_new_decisions),
            raw=result.raw,
        )
        return result

    # ------------------------------------------------------------------ #
    # Turn types
    # ------------------------------------------------------------------ #
    def run_morning_research(self) -> AgentTurnResult:
        return self._run(
            prompts.morning_research_prompt(self.universe, self.held_symbols()),
            "research",
            model=self.research_model,
            timeout=self.research_timeout,
        )

    def run_intraday(self, brief: str | None = None) -> AgentTurnResult:
        """Scheduled intraday turn. F3: when ``brief`` is supplied (assembled by
        the daemon from the snapshot + cached market data), it is injected and we
        do NOT call ``held_symbols()`` (a broker hit on the turn thread, critic#6)
        — the brief already lists the book. Without a brief (steering disabled,
        NFR-8) it falls back to the legacy held-symbols prompt."""
        if brief is not None:
            return self._run(prompts.intraday_prompt(brief=brief), "intraday")
        return self._run(prompts.intraday_prompt(held=self.held_symbols()), "intraday")

    def run_wake(self, brief: str | None, events, *, timeout: float | None = None
                 ) -> AgentTurnResult:
        """Event-driven wake turn (F3 FR-4). ``events`` are the typed WakeEvents
        that fired; ``timeout`` bounds the turn's execution (the real cap on how
        long this holds the turn_lock — critic#2). Advisor-only, same journal/
        executor gate as every other turn."""
        reasons = [getattr(e, "reason", str(e)) for e in (events or [])]
        return self._run(prompts.wake_prompt(brief, reasons), "wake", timeout=timeout)

    def run_eod_review(self, outcomes: list[str] | None = None) -> AgentTurnResult:
        # `outcomes` are richer (levels vs price, P&L) when the caller assembles
        # them from the broker; otherwise fall back to a plain decision list.
        if outcomes is None:
            outcomes = [f"{d.symbol} {d.action}" for d in self.journal.read_decisions()[-20:]]
        return self._run(prompts.eod_review_prompt(outcomes), "eod")

    def run_reconcile(self, context: str = "") -> AgentTurnResult:
        """Out-of-band turn after a human intervention (F4 FR-6): the agent
        re-reads live broker state + the human context and updates its journal /
        per-symbol theses / watchlist / resting protection so they don't drift.
        It must NOT open new discretionary positions -- only reconcile records and
        protective stops. Serialized with scheduled turns via the TurnCoordinator."""
        held = ", ".join(self.held_symbols()) or "none"
        prompt = (
            "A human operator just intervened in the LIVE account. Reconcile your "
            "journal, per-symbol theses, watchlist, and resting protection with the "
            "ACTUAL current broker state (use your tools to check positions/orders). "
            "Do NOT open new discretionary positions; only update your records and "
            "protective stops so they match reality, and acknowledge the human's intent.\n\n"
            f"Currently held (broker): {held}\n"
            f"Human intervention context:\n{context or '(see human_directives.jsonl)'}\n"
        )
        return self._run(prompt, "reconcile")

    # ------------------------------------------------------------------ #
    def schedule(self, scheduler, intraday_minutes: int = 30) -> None:
        """Register the daily turns on a TradingScheduler (market-hours cron)."""
        scheduler.add_market_open_job(self.run_morning_research, job_id="agent_morning")
        scheduler.add_batch_job(
            self.run_intraday, interval_minutes=intraday_minutes, job_id="agent_intraday"
        )
        scheduler.add_market_close_job(self.run_eod_review, job_id="agent_eod")
        logger.info(f"Agent loop scheduled (intraday every {intraday_minutes} min)")
