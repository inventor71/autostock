"""SteeringRuntime: assembles the F4 daemon-side engine and exposes daemon jobs.

Bundles channel + state + bus + coordinator + reconcile worker + command handler,
and provides the periodic jobs the scheduler drives: poll the file-drop channel,
publish the snapshot, drain off-hours trades at the open, and the ET-midnight sweep.
All broker access (commands + snapshot) runs on the single CommandBus worker
(NFR-2). Constructed only when steering is enabled; if absent, the daemon behaves
exactly as before (NFR-8).
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from src.agent.steering.bus import CommandBus
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler
from src.agent.steering.records import EMERGENCY_VERBS
from src.agent.steering.security import (
    TOKEN_ENV_VAR,
    issue_token,
    write_agent_hook_settings,
)
from src.agent.steering.state import SteeringState
from src.agent.steering.turns import ReconcileWorker, TurnCoordinator

# repo root: src/agent/steering/runtime.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STEERING_DIR = _REPO_ROOT / "steering"


class SteeringRuntime:
    def __init__(self, executor, orchestrator, *, steering_dir: str | Path | None = None,
                 token: str | None = None):
        self.executor = executor
        self.orchestrator = orchestrator
        self.steering_dir = Path(steering_dir) if steering_dir else DEFAULT_STEERING_DIR
        # Honor a pre-set STEERING_OPERATOR_TOKEN (from .env / the daemon's shell) so the
        # SEPARATELY-launched console can share ONE secret with the daemon; only generate a
        # random one when none is provided. (Previously this always generated a random token
        # and start() overwrote the env value -> the console's token never matched -> the
        # channel rejected every command as "bad token" -> end-to-end steering silently failed.)
        # session._invoke still scrubs this var from the AGENT's env (BR-10.2).
        self.token = token or os.environ.get(TOKEN_ENV_VAR) or issue_token()
        self.channel = SteeringChannel(self.steering_dir, self.token)
        self.state = SteeringState(executor.journal.root)
        self.bus = CommandBus()
        self.coordinator = TurnCoordinator()
        self.reconcile_worker = ReconcileWorker(self.coordinator)
        self.handler = CommandHandler(
            self.channel, self.state, executor,
            reconcile_worker=self.reconcile_worker, reconcile_run_fn=self._reconcile_run_fn,
        )
        self._pushed_questions: set[str] = set()

    # ---- lifecycle -------------------------------------------------------- #
    def start(self) -> None:
        # Publish the token to THIS process's env so a child operator tool (Unit B)
        # inherits it out-of-band; it is scrubbed from the agent's env on spawn
        # (session._invoke -> scrub_agent_env). Never written to a file / logged.
        os.environ[TOKEN_ENV_VAR] = self.token
        write_agent_hook_settings(self.executor.journal.root)  # BR-10.1 confinement
        self.bus.start()
        logger.info("Steering runtime started (channel={}, hook installed)", self.steering_dir)

    def stop(self) -> None:
        self.reconcile_worker.stop()
        self.bus.stop()

    # ---- reconcile -------------------------------------------------------- #
    def _reconcile_run_fn(self):
        return self.orchestrator.run_reconcile(self._recent_context())

    def _recent_context(self) -> str:
        directives = "; ".join(d.text for d in self.state.active_directives()) or "none"
        log = self.executor.journal.root / "human_directives.jsonl"
        recent = ""
        if log.exists():
            recent = "\n".join(log.read_text(encoding="utf-8").splitlines()[-8:])
        return f"Active directives: {directives}\nRecent interventions:\n{recent}"

    # ---- scheduler jobs --------------------------------------------------- #
    def poll_commands(self) -> None:
        """Read new file-drop commands and enqueue each on the worker (emergency
        verbs to the emergency lane). Best-effort: never raise into the scheduler."""
        try:
            for cmd in self.channel.read_new_commands():
                emergency = cmd.verb in EMERGENCY_VERBS
                self.bus.submit(lambda c=cmd: self.handler.handle(c), emergency=emergency)
        except Exception as e:
            logger.error("steering poll failed (continuing): {}", e)

    def publish_snapshot(self) -> None:
        """Publish the live read view. Broker access runs on the worker (NFR-2)."""
        def _build():
            broker = self.executor.broker
            try:
                ps = broker.get_portfolio_state()
                positions = {s: {"qty": p.qty, "avg_entry_price": p.avg_entry_price}
                             for s, p in ps.positions.items()}
                opens = [{"symbol": o.symbol, "order_id": o.order_id,
                          "stop_price": o.stop_price, "limit_price": o.limit_price}
                         for o in broker.get_open_orders()]
                market_open = broker.is_market_open()
            except Exception as e:
                logger.warning("snapshot build failed (skipping): {}", e)
                return
            self.channel.publish_snapshot({
                "run_state": self.state.run_state().model_dump(mode="json"),
                "locked_symbols": {s: self.state.lock_status(s) for s in positions},
                "pending": [p.model_dump(mode="json") for p in self.state.list_pending()],
                "positions": positions,
                "open_orders": opens,
                "market_open": market_open,
            })
        self.bus.submit(_build)

    def drain_offhours(self) -> None:
        """At the open: enqueue any off-hours trades queued overnight (BR-2.7)."""
        for cmd in self.channel.drain_offhours():
            self.bus.submit(lambda c=cmd: self.handler.handle(c))

    def poll_agent_questions(self) -> None:
        """FR-7: push newly-appended agent questions to the operator as events.
        Reads the agent-written file torn-safely; never rewrites it (critic #7)."""
        from src.agent.steering.jsonl import read_complete_lines
        from src.agent.steering.records import AgentQuestion, SteeringEvent

        path = self.executor.journal.root / "agent_questions.jsonl"
        try:
            lines, _ = read_complete_lines(path, 0)
            for line in lines:
                try:
                    q = AgentQuestion.model_validate_json(line)
                except Exception:
                    continue
                if q.id in self._pushed_questions:
                    continue
                self._pushed_questions.add(q.id)
                self.channel.append_event(SteeringEvent(
                    kind="agent_question",
                    payload={"id": q.id, "symbol": q.symbol, "text": q.text}))
        except Exception as e:
            logger.error("steering agent-question poll failed (continuing): {}", e)

    def daily_sweep(self) -> None:
        """ET-midnight: clear past-day locks/pending + re-scope channel (BR-4.8/critic #4)."""
        self.state.sweep_expired()
        self.channel.daily_reset()
        self._pushed_questions.clear()
