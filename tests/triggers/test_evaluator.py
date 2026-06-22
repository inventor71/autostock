"""U4 — TriggerEvaluator: due-ness, gating, fail-closed, rate-limit, coalesce.

Uses fakes (no docker, no network) so the loop logic is exercised in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.agent.triggers.evaluator import TriggerEvaluator
from src.agent.triggers.models import SourceRef, TriggerSpec, Verdict
from src.agent.triggers.sandbox import SandboxResult
from src.agent.triggers.store import TriggerStore

PREDICATE = "def should_fire(ctx):\n    return {'fire': True, 'why': 'x'}\n"


def _spec(tid="t", cadence="hourly", entry_inducing=True, days=7):
    return TriggerSpec(
        id=tid, thesis=f"thesis-{tid}", cadence=cadence, entry_inducing=entry_inducing,
        expires=datetime.now(timezone.utc) + timedelta(days=days),
        sources=[SourceRef(kind="signal", name="macro")],
    )


def _fire(why="fired"):
    return SandboxResult(verdict=Verdict(fire=True, why=why), error=None)


def _nofire():
    return SandboxResult(verdict=Verdict(fire=False), error=None)


def _err(category="predicate-raised"):
    return SandboxResult(verdict=Verdict(fire=False), error=category, detail="boom")


class FakeSandbox:
    def __init__(self, result):
        self._result = result
        self.calls = 0

    def run(self, src, ctx, *, timeout_s=None):
        self.calls += 1
        return self._result(src, ctx) if callable(self._result) else self._result


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def build_ctx(self, sources, *, now=None):
        self.calls += 1
        return {"macro": {"vix": 30}}


class FakeWorker:
    def __init__(self):
        self.calls = []
        self.run_fn = None

    def trigger(self, run_fn, *, kind="reconcile", timeout=None):
        self.calls.append((kind, timeout))
        self.run_fn = run_fn


@pytest.fixture
def harness(tmp_path):
    store = TriggerStore(root=tmp_path / "triggers")
    worker = FakeWorker()
    captured: list = []

    def make(result, run_state=None, **kw):
        return TriggerEvaluator(
            store=store, fetcher=FakeFetcher(), sandbox=FakeSandbox(result),
            run_state_fn=(lambda: run_state) if run_state is not None else None,
            reconcile_worker=worker, wake_runner=lambda evs: captured.append(evs) or "ran",
            **kw,
        )

    return SimpleNamespace(store=store, worker=worker, captured=captured, make=make)


def _run_state(paused=False, entries_halted=False):
    return SimpleNamespace(paused=paused, entries_halted=entries_halted)


# ---- fire path -------------------------------------------------------------- #

def test_fire_emits_agent_trigger_wake(harness):
    harness.store.register(_spec(), PREDICATE)
    ev = harness.make(_fire("vix>25"))
    ev.tick()

    assert harness.worker.calls == [("agent_trigger", 120.0)]
    # draining the lane runs the wake turn with the coalesced events
    harness.worker.run_fn()
    assert len(harness.captured) == 1
    (wake,) = harness.captured[0]
    assert wake.kind == "agent_trigger"
    assert wake.symbol == "MACRO"
    assert wake.reason == "vix>25"
    assert wake.payload == {"trigger_id": "t", "thesis": "thesis-t"}

    state = harness.store.load_state("t")
    assert state.fired_count == 1 and state.last_fired is not None and state.last_run is not None


def test_no_fire_records_run_but_no_wake(harness):
    harness.store.register(_spec(), PREDICATE)
    ev = harness.make(_nofire())
    ev.tick()
    assert harness.worker.calls == []
    assert harness.store.load_state("t").fired_count == 0
    assert harness.store.load_state("t").last_run is not None


# ---- gating (critic#3) ------------------------------------------------------ #

def test_paused_suppresses_all(harness):
    harness.store.register(_spec(), PREDICATE)
    ev = harness.make(_fire(), run_state=_run_state(paused=True))
    ev.tick()
    assert harness.worker.calls == []
    # paused short-circuits before evaluation: nothing ran
    assert harness.store.load_state("t").last_run is None


def test_entries_halted_suppresses_entry_inducing(harness):
    harness.store.register(_spec("entry", entry_inducing=True), PREDICATE)
    ev = harness.make(_fire(), run_state=_run_state(entries_halted=True))
    ev.tick()
    assert harness.worker.calls == []                       # wake suppressed
    assert harness.store.load_state("entry").last_run is not None  # but it WAS evaluated
    assert harness.store.load_state("entry").fired_count == 0


def test_entries_halted_allows_non_entry_inducing(harness):
    harness.store.register(_spec("protect", entry_inducing=False), PREDICATE)
    ev = harness.make(_fire(), run_state=_run_state(entries_halted=True))
    ev.tick()
    assert harness.worker.calls == [("agent_trigger", 120.0)]


def test_run_state_failure_suppresses(harness):
    harness.store.register(_spec(), PREDICATE)
    ev = TriggerEvaluator(
        store=harness.store, fetcher=FakeFetcher(), sandbox=FakeSandbox(_fire()),
        run_state_fn=lambda: (_ for _ in ()).throw(RuntimeError("down")),
        reconcile_worker=harness.worker, wake_runner=lambda e: None,
    )
    ev.tick()
    assert harness.worker.calls == []  # treated as paused → suppressed


# ---- fail-closed / auto-disable -------------------------------------------- #

def test_consecutive_errors_auto_disable(harness):
    harness.store.register(_spec(), PREDICATE)
    ev = harness.make(_err(), max_consecutive_errors=3)
    for _ in range(3):
        # each tick: reset last_run so it's due again
        st = harness.store.load_state("t")
        st.last_run = None
        harness.store.update_state("t", st)
        ev.tick()
    state = harness.store.load_state("t")
    assert state.disabled is True
    assert state.consecutive_errors >= 3
    assert harness.worker.calls == []  # never fired on error


def test_error_then_success_resets_counter(harness):
    harness.store.register(_spec(), PREDICATE)
    results = iter([_err(), _nofire()])
    ev = harness.make(lambda s, c: next(results), max_consecutive_errors=5)
    ev.tick()
    assert harness.store.load_state("t").consecutive_errors == 1
    st = harness.store.load_state("t"); st.last_run = None; harness.store.update_state("t", st)
    ev.tick()
    assert harness.store.load_state("t").consecutive_errors == 0


# ---- rate-limit ------------------------------------------------------------- #

def test_rate_limited_repeat_fire(harness):
    harness.store.register(_spec(), PREDICATE)
    ev = harness.make(_fire(), min_fire_gap_s=10_000)
    ev.tick()                                   # fires
    assert len(harness.worker.calls) == 1
    st = harness.store.load_state("t"); st.last_run = None; harness.store.update_state("t", st)
    ev.tick()                                   # due again but within fire gap → suppressed
    assert len(harness.worker.calls) == 1
    assert harness.store.load_state("t").fired_count == 1


# ---- due-ness --------------------------------------------------------------- #

def test_not_due_skips_sandbox(harness):
    harness.store.register(_spec(cadence="hourly"), PREDICATE)
    st = harness.store.load_state("t")
    st.last_run = datetime.now(timezone.utc)     # just ran
    harness.store.update_state("t", st)
    sandbox = FakeSandbox(_fire())
    ev = TriggerEvaluator(
        store=harness.store, fetcher=FakeFetcher(), sandbox=sandbox,
        run_state_fn=None, reconcile_worker=harness.worker, wake_runner=lambda e: None,
    )
    ev.tick()
    assert sandbox.calls == 0                    # not due → not evaluated
    assert harness.worker.calls == []


# ---- coalesce (critic#4) ---------------------------------------------------- #

def test_multiple_fires_coalesce_into_one_wake(harness):
    harness.store.register(_spec("a"), PREDICATE)
    harness.store.register(_spec("b"), PREDICATE)
    ev = harness.make(_fire())
    ev.tick()
    assert harness.worker.calls == [("agent_trigger", 120.0)]  # ONE lane trigger
    harness.worker.run_fn()
    assert len(harness.captured) == 1
    ids = {e.payload["trigger_id"] for e in harness.captured[0]}
    assert ids == {"a", "b"}
