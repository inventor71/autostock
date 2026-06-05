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
from datetime import date
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


def _task_title(task: SubAgentTask) -> str:
    """A short label for a sub-agent, from the first phrase of its task (F41)."""
    head = (task.description or "").strip().split(":")[0].split(".")[0]
    words = head.split()
    return " ".join(words[:4]) if words else f"task {task.agent_index}"


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
shorting_enabled: bool = True,
signal_brief_provider: Callable[[], str | None] | None = None,    ):
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
        self._shorting_enabled = shorting_enabled  # F60: gates short prompt guidance
        # F61: optional callable that returns the market-signal brief text to
        # prepend to the research prompt. Fail-honest — any error → no brief.
        self._signal_brief_provider = signal_brief_provider
        self.last_new_decisions: list[Decision] = []
        self.last_kept: list[Decision] = []
        self.last_rejected: list[Decision] = []
        self.last_turn_id: str = ""
        self._on_turn_start: Callable[[str, str], None] | None = None
        self._on_turn_end: Callable[[], None] | None = None
        # F65: lesson efficacy is expensive to compute (collect_outcomes hits the
        # price provider), so cache it per session-day and reuse across turns.
        # (day, efficacy) cached as ONE tuple so the cross-thread swap is atomic:
        # a reader never observes a fresh day paired with a stale/half-built dict
        # (concurrent scheduler turns may both recompute — that's accepted; only
        # the torn read is prevented). No lock needed (single-attr assign is atomic).
        self._efficacy_cached: tuple[date, dict] | None = None
        # F64: constitution-bounded self-rewritten guidance, loaded lazily from
        # the Python-managed store. ``rewrite_fn`` stays None in v1 (inert) — the
        # machinery ships safe; providing a rewrite_fn activates self-rewriting.
        self._guidance = None  # GuidanceHistory | None
        self._rewrite_fn = None

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
        self, prompt: str, turn_type: str, model: str | None = None,
        timeout: float | None = None, event_reasons: list[str] | None = None,
    ) -> AgentTurnResult:
        from src.agent.turn_log import build_turn_summary, generate_turn_id, record_turn

        from datetime import datetime as _dt

        turns_path = self.journal.root / "turns.jsonl"
        turn_id = generate_turn_id(turns_path, turn_type)
        started_at = _dt.now().isoformat(timespec="seconds")
        self.last_turn_id = turn_id

        if self._on_turn_start:
            self._on_turn_start(turn_id, turn_type)

        # F64: prepend the constitution + evolvable guidance on guidance-bearing
        # turns only (not eod/reconcile).
        if turn_type in ("research", "intraday", "wake"):
            prompt = self._assemble_turn(prompt)

        # Must index the SAME list _stamp_new slices (read_decisions, which skips
        # malformed lines) — count_decisions counts raw lines, so with any
        # unparseable line it overshoots and the slice drops the new decisions.
        before = len(self.journal.read_decisions())
        result = None
        error = False
        try:
            result = self.session.run_turn(prompt, model=model, timeout=timeout)
        except Exception:
            error = True
            raise
        finally:
            try:
                self.last_new_decisions = self._stamp_new(before)
            except Exception as stamp_exc:
                logger.warning(f"stamp failed during {turn_type} turn: {stamp_exc}")
                all_d = self.journal.read_decisions()
                self.last_new_decisions = all_d[before:]
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
            llm_text = getattr(result, "result", "") if result is not None else ""
            summary = build_turn_summary(
                turn_type, self.last_new_decisions,
                llm_text=llm_text,
                event_reasons=event_reasons,
            )
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
    def _signal_brief(self) -> str | None:
        """F61: market-signal brief to prepend to the research prompt, or None.

        Fail-honest: a provider error never blocks the research turn."""
        if self._signal_brief_provider is None:
            return None
        try:
            return self._signal_brief_provider()
        except Exception as exc:
            logger.warning("signal brief provider failed, skipping: {}", exc)
            return None

    def run_morning_research(self) -> AgentTurnResult:
        if self._multi_agent_enabled and self._multi_agent_n >= 2:
            if self._multi_agent_mode == "parallel":
                return self._run_parallel_research()
            return self._run_sequential_research()
        return self._run(
            prompts.morning_research_prompt(
                self.universe, self.held_symbols(),
                shorting_enabled=self._shorting_enabled,
                signal_brief=self._signal_brief(),
            ),
            "research",
            model=self.research_model,
            timeout=self.research_timeout,
        )

    # -- F23: multi-agent research ----------------------------------------- #

    # -- F64: constitution-bounded guidance --------------------------------- #
    def _guidance_history(self):
        if self._guidance is None:
            from src.agent.self_rewrite import load_history
            self._guidance = load_history(self.journal.root)
        return self._guidance

    def _guidance_version(self) -> str:
        return self._guidance_history().current_version

    def _guidance_preamble(self) -> str:
        """Constitution + current evolvable guidance, prepended to guidance-bearing
        turns (morning/intraday/wake/research). Eval turns and EOD are excluded."""
        from src.agent.self_rewrite import build_guidance
        return build_guidance(self._guidance_history())

    def _assemble_turn(self, core: str, *, lessons: str = "") -> str:
        """The single prompt-assembly point for guidance-bearing turns:
        constitution/guidance preamble + core prompt + optional lesson context.
        Every decision-emitting turn routes through here so none silently skips
        the F64 guidance layer (the prior hand-concatenation at each call site
        was easy to miss on a new turn type)."""
        text = self._guidance_preamble() + "\n\n" + core
        if lessons:
            text += f"\n{lessons}"
        return text

    def _stamp_new(self, before: int) -> list[Decision]:
        """Read decisions the LLM just wrote, stamp the active guidance
        ``prompt_version`` onto them (the LLM can't know it), and re-persist the
        file atomically (F62). Runs between turns, so no race with the appender."""
        all_d = self.journal.read_decisions()
        new = all_d[before:]
        if new:
            ver = self._guidance_version()
            if any(d.prompt_version != ver for d in new):
                for d in new:
                    d.prompt_version = ver
                self.journal.restamp_decisions(all_d)
        return new

    def _lesson_efficacy(self) -> dict:
        """Per-lesson efficacy (F62), cached per day. Fail-safe: any error
        (e.g. the price provider being unreachable) yields {} so recall simply
        falls back to relevance + recency ranking — efficacy never breaks a turn.
        """
        today = date.today()
        cached = self._efficacy_cached  # single read — can't tear
        if cached is not None and cached[0] == today:
            return cached[1]
        eff: dict = {}
        try:
            from src.agent.efficacy import lesson_efficacy
            from src.agent.quality.collector import collect_outcomes

            eff = lesson_efficacy(collect_outcomes(self.journal))
        except Exception as exc:  # never let efficacy collection sink a turn
            logger.warning(f"lesson efficacy unavailable, recall uses recency/relevance: {exc}")
            eff = {}
        self._efficacy_cached = (today, eff)  # single atomic swap
        return eff

    def _get_lessons(self):
        """F65: situational recall. Instead of the last-N lessons by date, select
        the lessons most relevant to today's regime and ranked by demonstrated
        efficacy (F62). Returns a pre-ranked top-N list the prompts render with
        lesson_id so the agent can cite them back (``lessons_cited``)."""
        if not self._reflection_enabled:
            return []
        all_lessons = self.journal.read_lessons_jsonl()
        if not all_lessons:
            return []
        from src.agent.recall import build_fingerprint, recall_lessons

        fp = build_fingerprint(regime_text=self.journal.read_regime())
        return recall_lessons(
            all_lessons,
            fp,
            self._lesson_efficacy(),
            k=self._reflection_max_lessons,
            # rerank_fn left None for v1: deterministic pure ranking. The LLM
            # rerank turn is a documented activation point (recall.recall_lessons
            # accepts rerank_fn; fallback to this same order on any failure).
        )

    def _run_sequential_research(self) -> AgentTurnResult:
        from datetime import datetime as _dt

        from src.agent import agent_reports
        from src.agent.turn_log import build_turn_summary, generate_turn_id, record_turn

        n = self._multi_agent_n
        n_rounds = n - 1
        held = self.held_symbols()
        lessons = self._get_lessons()
        timeout = self.research_timeout
        per_round = timeout / (n_rounds + 1) if timeout else None

        turns_path = self.journal.root / "turns.jsonl"
        turn_id = generate_turn_id(turns_path, "research")
        started_at = _dt.now().isoformat(timespec="seconds")
        self.last_turn_id = turn_id
        if self._on_turn_start:
            self._on_turn_start(turn_id, "research")

        # F41: capture each round's evaluation so the operator can drill into the
        # cross-validation from the timeline overlay. ``agents`` holds the
        # non-synthesis rounds (initial + debates); the final synthesis is kept
        # separately in ``synthesis_text``.
        before = len(self.journal.read_decisions())
        agents: list[dict] = []
        result = None
        error = False
        try:
            r0 = self.session.run_turn(
                self._assemble_turn(prompts.multi_research_initial_prompt(
                    self.universe, held, self._research_signals, lessons, n_rounds,
                    max_lessons=self._reflection_max_lessons,
                    shorting_enabled=self._shorting_enabled,
                    signal_brief=self._signal_brief(),
                )),
                model=self.research_model,
                timeout=per_round,
            )
            agents.append(agent_reports.make_eval(
                index=0, label="Round 1 · Initial",
                role="Initial full-universe cross-validation pass",
                text=getattr(r0, "result", ""),
            ))

            for i in range(1, n_rounds):
                ri = self.session.run_turn(
                    prompts.debate_prompt(i, n_rounds),
                    model=self.research_model,
                    timeout=per_round,
                )
                agents.append(agent_reports.make_eval(
                    index=i, label=f"Round {i + 1} · Debate",
                    role=f"Debate round {i} — challenge and verify prior leans",
                    text=getattr(ri, "result", ""),
                ))

            result = self.session.run_turn(
                self._assemble_turn(
                    prompts.synthesis_prompt(n_rounds, signal_brief=self._signal_brief())),
                model=self.research_model,
                timeout=per_round,
            )
        except Exception:
            error = True
            self.session.reset_session()
            raise
        finally:
            try:
                self.last_new_decisions = self._stamp_new(before)
            except Exception as stamp_exc:
                logger.warning(f"stamp failed during sequential research: {stamp_exc}")
                all_d = self.journal.read_decisions()
                self.last_new_decisions = all_d[before:]
            for d in self.last_new_decisions:
                d.turn_id = turn_id
            self.last_kept, self.last_rejected = filter_in_universe(
                self.last_new_decisions, self.universe
            )
            for d in self.last_rejected:
                logger.warning(f"Out-of-universe: {d.symbol} {d.action}")
            logger.info(
                "Multi-agent sequential ({} rounds): {} decisions, {} kept",
                n_rounds + 1, len(self.last_new_decisions), len(self.last_kept),
            )
            if not self.last_new_decisions and not error:
                logger.warning(
                    "Multi-agent sequential synthesis produced 0 decisions — "
                    "the agent may have failed to write decisions.jsonl"
                )
            synthesis_text = getattr(result, "result", "") if result is not None else ""
            record_turn(
                turns_path, turn_type="research",
                model=self.research_model or getattr(self.session, "model", "unknown"),
                num_decisions=len(self.last_new_decisions),
                raw=result.raw if result is not None else None,
                turn_id=turn_id,
                summary=build_turn_summary(
                    "research", self.last_new_decisions, llm_text=synthesis_text,
                ),
                error=error, started_at=started_at,
            )
            agent_reports.write_agent_report(self.journal.root, agent_reports.build_report(
                turn_id=turn_id,
                ts=_dt.now().astimezone().isoformat(timespec="seconds"),
                mode="sequential", agents=agents, synthesis_text=synthesis_text,
            ))
            if self._on_turn_end:
                self._on_turn_end()
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
                       timeout: float, signal_brief: str | None = None) -> SubAgentReport:
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
                    signal_brief=signal_brief,
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

        # F61: assemble the market-signal brief ONCE (collect() is TTL-cached) and
        # hand it to every parallel sub-agent — the discovery sub-agent especially
        # must see today's movers/read-through before hunting new entries.
        signal_brief = self._signal_brief()

        workspaces: list[Path] = []
        reports: list[SubAgentReport] = []
        try:
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                futures = {}
                for task in tasks:
                    ws = self._create_isolated_workspace()
                    workspaces.append(ws)
                    futures[pool.submit(self._run_sub_agent, task, ws, sub_timeout, signal_brief)] = task
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
                prompts.morning_research_prompt(
                    self.universe, self.held_symbols(),
                    shorting_enabled=self._shorting_enabled,
                    signal_brief=self._signal_brief(),
                ),
                "research", model=self.research_model, timeout=max(total_timeout * 0.3, 60.0),
            )

        from datetime import datetime as _dt

        from src.agent import agent_reports
        from src.agent.turn_log import build_turn_summary, generate_turn_id, record_turn

        turns_path = self.journal.root / "turns.jsonl"
        turn_id = generate_turn_id(turns_path, "research")
        started_at = _dt.now().isoformat(timespec="seconds")
        self.last_turn_id = turn_id
        if self._on_turn_start:
            self._on_turn_start(turn_id, "research")

        lessons = self._get_lessons()
        lesson_ctx = prompts._build_lesson_context(
            lessons, max_n=self._reflection_max_lessons,
        ) if lessons else ""
        result = None
        error = False
        try:
            result = self.session.run_turn(
                self._assemble_turn(
                    prompts.parallel_synthesis_prompt(report_texts, signal_brief=signal_brief),
                    lessons=lesson_ctx),
                model=self.research_model,
                timeout=max(total_timeout * 0.3, 60.0),
            )
        except Exception:
            error = True
            raise
        finally:
            try:
                self.last_new_decisions = self._stamp_new(before)
            except Exception as stamp_exc:
                logger.warning(f"stamp failed during parallel research: {stamp_exc}")
                all_d = self.journal.read_decisions()
                self.last_new_decisions = all_d[before:]
            for d in self.last_new_decisions:
                d.turn_id = turn_id
            self.last_kept, self.last_rejected = filter_in_universe(
                self.last_new_decisions, self.universe
            )
            for d in self.last_rejected:
                logger.warning(f"Out-of-universe: {d.symbol} {d.action}")
            logger.info(
                "Multi-agent parallel ({} sub-agents, {} reports): {} decisions, {} kept",
                len(tasks), len(report_texts), len(self.last_new_decisions), len(self.last_kept),
            )
            if not self.last_new_decisions and not error:
                logger.warning(
                    "Multi-agent parallel synthesis produced 0 decisions — "
                    "the synthesis agent may have failed to write decisions.jsonl"
                )
            synthesis_text = getattr(result, "result", "") if result is not None else ""
            record_turn(
                turns_path, turn_type="research",
                model=self.research_model or getattr(self.session, "model", "unknown"),
                num_decisions=len(self.last_new_decisions),
                raw=result.raw if result is not None else None,
                turn_id=turn_id,
                summary=build_turn_summary(
                    "research", self.last_new_decisions, llm_text=synthesis_text,
                ),
                error=error, started_at=started_at,
            )
            # F41: one AgentEval per spawned sub-agent (sorted by index for stable
            # display); completed→ok, otherwise→error with the failure reason.
            agents = [
                agent_reports.make_eval(
                    index=r.agent_index,
                    label=f"Agent {r.agent_index + 1} · {_task_title(r.task)}",
                    role=r.task.description,
                    text=r.result_text,
                    status="ok" if r.completed else "error",
                    error=r.error,
                )
                for r in sorted(reports, key=lambda r: r.agent_index)
            ]
            agent_reports.write_agent_report(self.journal.root, agent_reports.build_report(
                turn_id=turn_id,
                ts=_dt.now().astimezone().isoformat(timespec="seconds"),
                mode="parallel", agents=agents, synthesis_text=synthesis_text,
            ))
            if self._on_turn_end:
                self._on_turn_end()
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
        return self._run(
            prompts.wake_prompt(brief, reasons), "wake",
            timeout=timeout, event_reasons=reasons,
        )

    def run_eod_review(self, outcomes: list[str] | None = None, surge_count: int = 0) -> AgentTurnResult:
        # `outcomes` are richer (levels vs price, P&L) when the caller assembles
        # them from the broker; otherwise fall back to a plain decision list.
        if outcomes is None:
            outcomes = [f"{d.symbol} {d.action}" for d in self.journal.read_decisions()[-20:]]
        result = self._run(prompts.eod_review_prompt(outcomes, surge_count=surge_count), "eod")
        self._run_self_rewrite()
        return result

    def _run_self_rewrite(self) -> None:
        """F64 EOD step: propose a guidance rewrite (inert unless ``_rewrite_fn``
        is set), then auto-rollback a degraded version. Fully guarded; any error
        is swallowed so it can never break the EOD turn."""
        try:
            from src.agent.efficacy import lesson_efficacy, prompt_version_efficacy
            from src.agent.quality.collector import collect_outcomes
            from src.agent.self_rewrite import (
                maybe_rollback,
                propose_rewrite,
                save_history,
                should_rewrite,
            )

            # Fuse: call collect_outcomes ONCE, feed both efficacy views.
            outcomes = collect_outcomes(self.journal)
            hist = self._guidance_history()
            eff = lesson_efficacy(outcomes)
            ver_eff = prompt_version_efficacy(outcomes)

            # Rollback: compare per-version avg_excess.
            cur = hist.current()
            changed = maybe_rollback(
                hist,
                {v: ve.avg_excess for v, ve in ver_eff.items()},
            )
            # Rewrite: gate + propose.
            cur_eff = ver_eff.get(cur.version)
            sample = cur_eff.applied_n if cur_eff else 0
            if self._rewrite_fn is not None and should_rewrite(hist, sample):
                res = propose_rewrite(hist, eff, rewrite_fn=self._rewrite_fn)
                changed = changed or res.action in ("adopted", "rejected")
            if changed:
                save_history(self.journal.root, hist)
        except Exception as exc:  # never let self-rewrite sink the EOD turn
            logger.warning(f"self-rewrite step skipped: {exc}")

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
