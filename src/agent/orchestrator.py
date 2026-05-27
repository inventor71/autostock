"""Slow-loop orchestrator: drives the PM agent's daily session.

This is the agentic path's own loop — deliberately NOT a ``BaseStrategy`` on
``TradingEngine`` (that engine is per-symbol; the PM reasons over the whole book
in one turn). It sequences the daily turn types (morning research / intraday /
EOD review), supplies live context (universe menu, held positions), and tracks
which decisions each turn produced. It writes only to the journal; reading
``decisions.jsonl`` and executing via RiskManager/Broker is Phase 3.
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.agent import prompts
from src.agent.journal import Decision, Journal
from src.agent.session import AgentSession, AgentTurnResult


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
        universe: list[str] | None = None,
        portfolio_provider: Callable[[], object] | None = None,
    ):
        self.session = session or AgentSession()
        self.journal: Journal = self.session.journal
        if universe is None:
            from config.config import get_settings
            universe = list(get_settings().trading.symbols)
        self.universe = universe
        # Optional source of real holdings (a broker); falls back to the journal's
        # tracked theses so the loop is usable before execution is wired (Phase 3).
        self.portfolio_provider = portfolio_provider

        # Populated after each turn for inspection / Phase 3 handoff.
        self.last_new_decisions: list[Decision] = []
        self.last_kept: list[Decision] = []
        self.last_rejected: list[Decision] = []

    # ------------------------------------------------------------------ #
    def held_symbols(self) -> list[str]:
        if self.portfolio_provider is not None:
            try:
                portfolio = self.portfolio_provider()
                positions = getattr(portfolio, "positions", None)
                if positions is not None:
                    return sorted(positions.keys())
            except Exception as exc:
                logger.warning(f"portfolio_provider failed, using journal: {exc}")
        return self.journal.list_positions()

    def _run(self, prompt: str, turn_type: str) -> AgentTurnResult:
        before = len(self.journal.read_decisions())
        result = self.session.run_turn(prompt)
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
            model=getattr(self.session, "model", "unknown"),
            num_decisions=len(self.last_new_decisions),
            raw=result.raw,
        )
        return result

    # ------------------------------------------------------------------ #
    # Turn types
    # ------------------------------------------------------------------ #
    def run_morning_research(self) -> AgentTurnResult:
        return self._run(prompts.morning_research_prompt(self.universe, self.held_symbols()), "research")

    def run_intraday(self, quotes: dict[str, float] | None = None) -> AgentTurnResult:
        return self._run(prompts.intraday_prompt(quotes, self.held_symbols()), "intraday")

    def run_eod_review(self, outcomes: list[str] | None = None) -> AgentTurnResult:
        # `outcomes` are richer (levels vs price, P&L) when the caller assembles
        # them from the broker; otherwise fall back to a plain decision list.
        if outcomes is None:
            outcomes = [f"{d.symbol} {d.action}" for d in self.journal.read_decisions()[-20:]]
        return self._run(prompts.eod_review_prompt(outcomes), "eod")

    # ------------------------------------------------------------------ #
    def schedule(self, scheduler, intraday_minutes: int = 30) -> None:
        """Register the daily turns on a TradingScheduler (market-hours cron)."""
        scheduler.add_market_open_job(self.run_morning_research, job_id="agent_morning")
        scheduler.add_batch_job(
            self.run_intraday, interval_minutes=intraday_minutes, job_id="agent_intraday"
        )
        scheduler.add_market_close_job(self.run_eod_review, job_id="agent_eod")
        logger.info(f"Agent loop scheduled (intraday every {intraday_minutes} min)")
