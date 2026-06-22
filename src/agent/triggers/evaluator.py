"""TriggerEvaluator — the slow-cadence loop that evaluates triggers and self-wakes (U4).

Runs as a daemon scheduler job (alongside the 5s WakeDetector, but on a coarse tick).
For each *due* active trigger it: brokers ``ctx`` → runs the predicate in the sandbox
→ persists state → and, on ``fire``, buffers a ``WakeEvent(kind="agent_trigger")``.
After the sweep, buffered events are handed to the shared ``ReconcileWorker`` on a
dedicated ``"agent_trigger"`` lane (so it never clobbers the WakeDetector's ``"wake"``
lane) which serializes the actual wake turn through the TurnCoordinator.

Critical safety properties (critic findings reflected):

* **Gating is NOT inherited — it is enforced here (critic#3).** ``gate.py`` does not
  block on halt state, and this evaluator is a different component than WakeDetector,
  so it independently reads ``run_state`` and applies the same suppression:
  ``paused`` → drop all wakes; ``entries_halted`` → drop ``entry_inducing`` triggers.
  Omitting this would let a macro trigger induce a BUY during a halt.
* **Fail-closed (SECURITY-15).** A sandbox error never fires; it increments the
  consecutive-error counter and auto-disables the trigger after a threshold so a
  permanently-broken predicate stops costing evaluations.
* **Rate-limited fires.** A persistently-true trigger won't wake every cadence tick;
  ``min_fire_gap_s`` throttles repeat fires.
* **Coalesce within the lane, compete across lanes (critic#4).** Multiple triggers
  firing in one sweep coalesce into ONE wake turn (buffer drained at fire time);
  the ``agent_trigger`` lane competes with the ``wake`` lane for the turn lock and
  yields/times out rather than clobbering it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from loguru import logger

from src.agent.intraday.records import WakeEvent
from src.agent.triggers.fetch import BrokeredFetcher
from src.agent.triggers.models import TriggerSpec
from src.agent.triggers.sandbox import SandboxRunner
from src.agent.triggers.store import TriggerStore

_CADENCE_SECONDS = {"hourly": 3600, "daily": 86400}


class _RunStateLike(Protocol):
    paused: bool
    entries_halted: bool


class _ReconcileWorkerLike(Protocol):
    def trigger(self, run_fn: Callable[[], Any], *, kind: str = ..., timeout: float | None = ...) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TriggerEvaluator:
    def __init__(
        self,
        *,
        store: TriggerStore,
        fetcher: BrokeredFetcher,
        sandbox: SandboxRunner,
        run_state_fn: Callable[[], _RunStateLike] | None,
        reconcile_worker: _ReconcileWorkerLike,
        wake_runner: Callable[[list[WakeEvent]], Any],
        clock: Callable[[], datetime] = _utcnow,
        wake_timeout: float = 120.0,
        sandbox_timeout: float | None = None,
        max_consecutive_errors: int = 5,
        min_fire_gap_s: float = 6 * 3600,
        due_slack_s: float = 30.0,
    ):
        self._store = store
        self._fetcher = fetcher
        self._sandbox = sandbox
        self._run_state_fn = run_state_fn
        self._worker = reconcile_worker
        self._wake_runner = wake_runner
        self._clock = clock
        self._wake_timeout = wake_timeout
        self._sandbox_timeout = sandbox_timeout
        self._max_errors = max_consecutive_errors
        self._min_fire_gap = min_fire_gap_s
        self._due_slack = due_slack_s
        self._buffer: list[WakeEvent] = []

    # ---- scheduler entry point --------------------------------------------- #
    def tick(self) -> None:
        """Evaluate all due triggers once. Best-effort: never raises (NFR — must
        not kill the scheduler thread)."""
        try:
            rs = self._run_state()
            if rs is not None and getattr(rs, "paused", False):
                logger.info("trigger eval suppressed: run paused")
                return
            now = self._clock()
            entries_halted = bool(rs is not None and getattr(rs, "entries_halted", False))
            fired: list[WakeEvent] = []
            for spec in self._store.active_specs(now):
                ev = self._evaluate_one(spec, now, entries_halted)
                if ev is not None:
                    fired.append(ev)
            if not fired:
                return
            with_kinds = ", ".join(e.payload.get("trigger_id", "?") for e in fired)
            logger.info("trigger eval: {} trigger(s) fired ({})", len(fired), with_kinds)
            self._buffer.extend(fired)
            self._worker.trigger(self._fire, kind="agent_trigger", timeout=self._wake_timeout)
        except Exception as e:  # never kill the scheduler (mirrors WakeDetector)
            logger.error("trigger eval tick failed (continuing): {}", e)

    def _fire(self) -> Any:
        # Drain at fire time so triggers that fired across the sweep coalesce into
        # ONE wake turn (mirrors WakeDetector._fire_wake).
        events, self._buffer = self._buffer, []
        if not events:
            return None
        for ev in events:
            logger.info("trigger wake fire: id={} reason={}", ev.payload.get("trigger_id"), ev.reason)
        return self._wake_runner(events)

    # ---- per-trigger evaluation -------------------------------------------- #
    def _evaluate_one(self, spec: TriggerSpec, now: datetime, entries_halted: bool) -> WakeEvent | None:
        state = self._store.load_state(spec.id)
        if not self._due(spec, state.last_run, now):
            return None

        ctx = self._fetcher.build_ctx(spec.sources, now=now)
        predicate_src = self._store.load_predicate(spec.id)
        result = self._sandbox.run(predicate_src, ctx, timeout_s=self._sandbox_timeout)

        state.last_run = now
        state.last_verdict = result.verdict
        wake: WakeEvent | None = None

        if not result.ok:
            state.consecutive_errors += 1
            logger.warning(
                "trigger {} eval error ({}/{}): {} — {}",
                spec.id, state.consecutive_errors, self._max_errors, result.error, result.detail,
            )
            if state.consecutive_errors >= self._max_errors:
                state.disabled = True
                state.disabled_reason = f"{self._max_errors} consecutive errors (last: {result.error})"
                logger.error("trigger {} auto-disabled: {}", spec.id, state.disabled_reason)
        else:
            state.consecutive_errors = 0
            if result.verdict.fire:
                wake = self._maybe_wake(spec, state, result.verdict.why, now, entries_halted)

        self._store.update_state(spec.id, state)
        return wake

    def _maybe_wake(self, spec, state, why, now, entries_halted) -> WakeEvent | None:
        # Gating (critic#3): entries_halted drops entry-inducing triggers — the only
        # backstop, since gate.py doesn't enforce halts.
        if entries_halted and spec.entry_inducing:
            logger.info("trigger {} fired but suppressed (entries halted)", spec.id)
            return None
        # Rate-limit: don't re-wake on every cadence tick while a trigger stays true.
        if state.last_fired is not None:
            gap = (now - state.last_fired).total_seconds()
            if gap < self._min_fire_gap:
                logger.info("trigger {} fired but rate-limited ({:.0f}s < {:.0f}s)",
                            spec.id, gap, self._min_fire_gap)
                return None
        state.fired_count += 1
        state.last_fired = now
        return WakeEvent(
            kind="agent_trigger",
            symbol=spec.wake_symbol(),
            reason=why or spec.thesis,
            payload={"trigger_id": spec.id, "thesis": spec.thesis},
            entry_inducing=spec.entry_inducing,
        )

    # ---- helpers ----------------------------------------------------------- #
    def _due(self, spec: TriggerSpec, last_run: datetime | None, now: datetime) -> bool:
        if last_run is None:
            return True
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        interval = _CADENCE_SECONDS[spec.cadence]
        return (now - last_run).total_seconds() >= (interval - self._due_slack)

    def _run_state(self):
        if self._run_state_fn is None:
            return None
        try:
            return self._run_state_fn()
        except Exception as e:  # gating is best-effort readable; fail toward suppression
            logger.warning("trigger eval: run_state unavailable ({}); suppressing wakes", e)
            class _Paused:
                paused = True
                entries_halted = True
            return _Paused()
