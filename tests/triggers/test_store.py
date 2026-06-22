"""U1 — TriggerStore CRUD + lifecycle filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agent.triggers.models import SourceRef, TriggerSpec, TriggerState
from src.agent.triggers.store import (
    MAX_TRIGGERS,
    PREDICATE_MAX_BYTES,
    TriggerError,
    TriggerStore,
)

PREDICATE = (
    "def should_fire(ctx):\n"
    "    return {'fire': False, 'why': 'noop'}\n"
)


def _spec(tid: str = "vix-spike", days: int = 7, **kw) -> TriggerSpec:
    return TriggerSpec(
        id=tid, thesis="VIX regime shift", cadence="hourly",
        expires=datetime.now(timezone.utc) + timedelta(days=days),
        sources=[SourceRef(kind="signal", name="macro")], **kw,
    )


@pytest.fixture
def store(tmp_path):
    return TriggerStore(root=tmp_path / "triggers")


def test_register_then_roundtrip(store):
    spec = _spec()
    store.register(spec, PREDICATE)
    assert store.exists("vix-spike")
    loaded = store.load_spec("vix-spike")
    assert loaded == spec
    assert store.load_predicate("vix-spike") == PREDICATE
    assert store.load_state("vix-spike") == TriggerState()


def test_register_renders_human_view(store):
    store.register(_spec(), PREDICATE)
    md = (store.root / "vix-spike" / "trigger.md").read_text()
    assert "# trigger: vix-spike" in md
    assert "VIX regime shift" in md


def test_duplicate_register_rejected(store):
    store.register(_spec(), PREDICATE)
    with pytest.raises(TriggerError):
        store.register(_spec(), PREDICATE)


def test_expired_spec_rejected(store):
    with pytest.raises(TriggerError):
        store.register(_spec(days=-1), PREDICATE)


def test_oversize_predicate_rejected(store):
    big = "def should_fire(ctx):\n    x = '" + "a" * PREDICATE_MAX_BYTES + "'\n    return {'fire': False}\n"
    with pytest.raises(TriggerError):
        store.register(_spec(), big)


def test_screen_failure_rejected_with_violations(store):
    bad = "import os\ndef should_fire(ctx):\n    return {'fire': False}\n"
    with pytest.raises(TriggerError) as ei:
        store.register(_spec(), bad)
    assert ei.value.violations  # carries machine-readable violations for agent feedback


def test_list_and_inspect(store):
    store.register(_spec("a"), PREDICATE)
    store.register(_spec("b"), PREDICATE)
    ids = {s.id for s in store.list()}
    assert ids == {"a", "b"}
    detail = store.inspect("a")
    assert detail.spec.id == "a"
    assert detail.predicate_src == PREDICATE
    assert detail.state.fired_count == 0


def test_cancel(store):
    store.register(_spec(), PREDICATE)
    assert store.cancel("vix-spike") is True
    assert not store.exists("vix-spike")
    assert store.cancel("vix-spike") is False  # idempotent-ish: already gone


def test_update_state_persists(store):
    store.register(_spec(), PREDICATE)
    st = store.load_state("vix-spike")
    st.fired_count = 3
    st.disabled = True
    store.update_state("vix-spike", st)
    assert store.load_state("vix-spike").fired_count == 3
    assert store.load_state("vix-spike").disabled is True


def test_update_state_unknown_id_raises(store):
    with pytest.raises(TriggerError):
        store.update_state("ghost", TriggerState())


def test_active_specs_excludes_expired_and_disabled(store, tmp_path):
    store.register(_spec("live"), PREDICATE)
    store.register(_spec("doomed"), PREDICATE)
    # disable one
    st = store.load_state("doomed")
    st.disabled = True
    store.update_state("doomed", st)
    active_ids = {s.id for s in store.active_specs()}
    assert active_ids == {"live"}


def test_active_specs_excludes_expired_via_now(store):
    store.register(_spec("soon", days=1), PREDICATE)
    # ask "is anything active 2 days from now?" → the 1-day trigger has expired
    future_now = datetime.now(timezone.utc) + timedelta(days=2)
    assert store.active_specs(now=future_now) == []


def test_ids_empty_when_no_root(tmp_path):
    s = TriggerStore(root=tmp_path / "nope")
    assert s.ids() == []
    assert s.count() == 0


def test_max_triggers_backstop(store, monkeypatch):
    # Lower the cap so the test stays fast.
    monkeypatch.setattr("src.agent.triggers.store.MAX_TRIGGERS", 2)
    store.register(_spec("a"), PREDICATE)
    store.register(_spec("b"), PREDICATE)
    with pytest.raises(TriggerError):
        store.register(_spec("c"), PREDICATE)
