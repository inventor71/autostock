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

import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loguru import logger

from src.agent import prompts
from src.agent.journal import Decision, Journal
from src.agent.session import AgentSession, AgentTurnResult
from src.core.models import PortfolioState


@dataclass
class SubAgentTask:
    agent_index: int
    description: str
    focus_symbols: list[str] = field(default_factory=list)


@dataclass
class SubAgentReport:
    agent_index: int
    task: SubAgentTask
    result_text: str
    completed: bool
    error: str | None = None


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
        multi_agent_enabled: bool = False,
        multi_agent_mode: str = "sequential",
        multi_agent_n: int = 3,
        research_signals: list[str] | None = None,
        reflection_enabled: bool = True,
        reflection_max_lessons: int = 10,
    ):
        self.session = session or AgentSession()
        self.journal: Journal = self.session.journal
        self.universe = universe
        self.research_model = research_model
        self.research_timeout = research_timeout
        self.portfolio_provider = portfolio_provider
        self._multi_agent_enabled = multi_agent_enabled
        self._multi_agent_mode = multi_agent_mode
        self._multi_agent_n = multi_agent_n
        self._research_signals = research_signals
        self._reflection_enabled = reflection_enabled
        self._reflection_max_lessons = reflection_max_lessons

        self.last_new_decisions: list[Decision] = []
        self.last_kept: list[Decision] = []
        self.last_rejected: list[Decision] = []
        self.last_turn_id: str = ""
        self._on_turn_start: Callable[[str, str], None] | None = None
        self._on_turn_end: Callable[[], None] | None = None

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
        from src.agent.turn_log import build_turn_summary, generate_turn_id, record_turn

        from datetime import datetime as _dt

        turns_path = self.journal.root / "turns.jsonl"
        turn_id = generate_turn_id(turns_path, turn_type)
        started_at = _dt.now().isoformat(timespec="seconds")
        self.last_turn_id = turn_id

        if self._on_turn_start:
            self._on_turn_start(turn_id, turn_type)

        before = len(self.journal.read_decisions())
        result = None
        error = False
        try:
            result = self.session.run_turn(prompt, model=model, timeout=timeout)
        except Exception:
            error = True
            raise
        finally:
            self.last_new_decisions = self.journal.read_decisions()[before:]
            for d in self.last_new_decisions:
                d.turn_id = turn_id
            self.last_kept, self.last_rejected = filter_in_universe(
                self.last_new_decisions, self.universe
            )
            for d in self.last_rejected:
                logger.warning(
                    f"Out-of-universe decision will be rejected at execution: "
                    f"{d.symbol} {d.action}"
                )
            logger.info(
                "Turn [{}] produced {} decision(s); {} in-universe, {} rejected",
                turn_id,
                len(self.last_new_decisions), len(self.last_kept), len(self.last_rejected),
            )
            summary = build_turn_summary(turn_type, self.last_new_decisions)
            raw = result.raw if result is not None else None
            record_turn(
                turns_path,
                turn_type=turn_type,
                model=model or getattr(self.session, "model", "unknown"),
                num_decisions=len(self.last_new_decisions),
                raw=raw,
                turn_id=turn_id,
                summary=summary,
                error=error,
                started_at=started_at,
            )
            if self._on_turn_end:
                self._on_turn_end()
        return result

    # ------------------------------------------------------------------ #
    # Turn types
    # ------------------------------------------------------------------ #
    def run_morning_research(self) -> AgentTurnResult:
        if self._multi_agent_enabled and self._multi_agent_n >= 2:
            if self._multi_agent_mode == "parallel":
                return self._run_parallel_research()
            return self._run_sequential_research()
        return self._run(
            prompts.morning_research_prompt(self.universe, self.held_symbols()),
            "research",
            model=self.research_model,
            timeout=self.research_timeout,
        )

    # -- F23: multi-agent research ----------------------------------------- #

    def _get_lessons(self):
        if not self._reflection_enabled:
            return []
        return self.journal.read_lessons_jsonl()

    def _run_sequential_research(self) -> AgentTurnResult:
        n = self._multi_agent_n
        n_rounds = n - 1
        held = self.held_symbols()
        lessons = self._get_lessons()
        timeout = self.research_timeout
        per_round = timeout / (n_rounds + 1) if timeout else None

        before = len(self.journal.read_decisions())

        try:
            self.session.run_turn(
                prompts.multi_research_initial_prompt(
                    self.universe, held, self._research_signals, lessons, n_rounds,
                    max_lessons=self._reflection_max_lessons,
                ),
                model=self.research_model,
                timeout=per_round,
            )

            for i in range(1, n_rounds):
                self.session.run_turn(
                    prompts.debate_prompt(i, n_rounds),
                    model=self.research_model,
                    timeout=per_round,
                )

            result = self.session.run_turn(
                prompts.synthesis_prompt(n_rounds),
                model=self.research_model,
                timeout=per_round,
            )
        except Exception:
            self.session.reset_session()
            raise

        self.last_new_decisions = self.journal.read_decisions()[before:]
        self.last_kept, self.last_rejected = filter_in_universe(
            self.last_new_decisions, self.universe
        )
        for d in self.last_rejected:
            logger.warning(f"Out-of-universe: {d.symbol} {d.action}")
        logger.info(
            "Multi-agent sequential ({} rounds): {} decisions, {} kept",
            n_rounds + 1, len(self.last_new_decisions), len(self.last_kept),
        )
        if not self.last_new_decisions:
            logger.warning(
                "Multi-agent sequential synthesis produced 0 decisions — "
                "the agent may have failed to write decisions.jsonl"
            )
        from src.agent.turn_log import record_turn
        record_turn(
            self.journal.root / "turns.jsonl", turn_type="research",
            model=self.research_model or getattr(self.session, "model", "unknown"),
            num_decisions=len(self.last_new_decisions), raw=result.raw,
        )
        return result

    def _create_isolated_workspace(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="autostock_sub_"))
        for name in ("CLAUDE.md", "lessons.md", "regime.md", "watchlist.md"):
            src = self.journal.root / name
            if src.exists():
                shutil.copy2(src, tmp / name)
        if self.journal.positions_dir.exists():
            shutil.copytree(self.journal.positions_dir, tmp / "positions")
        return tmp

    def _plan_sub_tasks(self) -> list[SubAgentTask]:
        n = self._multi_agent_n - 1
        held = self.held_symbols()
        tasks = []
        if n >= 1:
            tasks.append(SubAgentTask(
                0, f"Review all held positions ({', '.join(held) or 'none'}) — "
                "pull fresh indicators, news, fundamentals for each. Evaluate "
                "whether to HOLD, SELL, or ADJUST_STOP.",
                focus_symbols=held,
            ))
        if n >= 2:
            tasks.append(SubAgentTask(
                1, "Discovery: scan the scoreboard for the full universe, identify "
                "the top candidates for new BUY entries. Deep-dive promising names "
                "with indicators, fundamentals, news, and earnings data.",
            ))
        for i in range(2, n):
            tasks.append(SubAgentTask(
                i, f"Supplementary analysis #{i - 1}: regime assessment (macro tool), "
                "cross-check held positions' theses against sector rotation, "
                "and flag any earnings-event risks within 5 days.",
            ))
        return tasks

    def _run_sub_agent(self, task: SubAgentTask, workspace: Path,
                       timeout: float) -> SubAgentReport:
        try:
            sub = AgentSession.create_sub_agent(
                workspace=workspace,
                model=self.research_model or "sonnet",
                timeout=timeout,
                runner=self.session._runner,
            )
            result = sub.run_turn(
                prompts.sub_agent_prompt(
                    task.description, self.universe, self._research_signals,
                ),
                model=self.research_model,
                timeout=timeout,
            )
            return SubAgentReport(task.agent_index, task, result.result, True)
        except Exception as exc:
            logger.warning(f"Sub-agent {task.agent_index} failed: {exc}")
            return SubAgentReport(task.agent_index, task, "", False, str(exc))

    def _run_parallel_research(self) -> AgentTurnResult:
        tasks = self._plan_sub_tasks()
        total_timeout = self.research_timeout or 3300.0
        sub_timeout = total_timeout * 0.7

        before = len(self.journal.read_decisions())

        workspaces: list[Path] = []
        reports: list[SubAgentReport] = []
        try:
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                futures = {}
                for task in tasks:
                    ws = self._create_isolated_workspace()
                    workspaces.append(ws)
                    futures[pool.submit(self._run_sub_agent, task, ws, sub_timeout)] = task
                for f in as_completed(futures, timeout=sub_timeout + 30):
                    try:
                        reports.append(f.result())
                    except Exception as exc:
                        t = futures[f]
                        reports.append(SubAgentReport(t.agent_index, t, "", False, str(exc)))
        except TimeoutError:
            logger.warning("Sub-agent timeout; synthesizing with partial results")
        finally:
            for ws in workspaces:
                shutil.rmtree(ws, ignore_errors=True)

        report_texts = [r.result_text for r in reports if r.completed and r.result_text]
        if not report_texts:
            logger.warning("No sub-agent reports; falling back to single-session research")
            return self._run(
                prompts.morning_research_prompt(self.universe, self.held_symbols()),
                "research", model=self.research_model, timeout=max(total_timeout * 0.3, 60.0),
            )

        lessons = self._get_lessons()
        lesson_ctx = prompts._build_lesson_context(
            lessons, max_n=self._reflection_max_lessons,
        ) if lessons else ""
        result = self.session.run_turn(
            prompts.parallel_synthesis_prompt(report_texts)
            + (f"\n{lesson_ctx}" if lesson_ctx else ""),
            model=self.research_model,
            timeout=max(total_timeout * 0.3, 60.0),
        )

        self.last_new_decisions = self.journal.read_decisions()[before:]
        self.last_kept, self.last_rejected = filter_in_universe(
            self.last_new_decisions, self.universe
        )
        for d in self.last_rejected:
            logger.warning(f"Out-of-universe: {d.symbol} {d.action}")
        logger.info(
            "Multi-agent parallel ({} sub-agents, {} reports): {} decisions, {} kept",
            len(tasks), len(report_texts), len(self.last_new_decisions), len(self.last_kept),
        )
        if not self.last_new_decisions:
            logger.warning(
                "Multi-agent parallel synthesis produced 0 decisions — "
                "the synthesis agent may have failed to write decisions.jsonl"
            )
        from src.agent.turn_log import record_turn
        record_turn(
            self.journal.root / "turns.jsonl", turn_type="research",
            model=self.research_model or getattr(self.session, "model", "unknown"),
            num_decisions=len(self.last_new_decisions), raw=result.raw,
        )
        return result

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
