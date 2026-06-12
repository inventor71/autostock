"""F44 Unit 1 — TurnCoordinator manual-turn dedup.

A same-type manual turn that is already running (the in-flight turn — auto or manual)
or already queued must NOT be re-enqueued: the coordinator returns "already_running" /
"already_queued" instead of stacking a duplicate. Different types are unaffected.

Includes a property-based invariant (hypothesis): across any random sequence of
triggers, at most one accepted (started/queued) entry exists per turn type, and the
pending-key set equals exactly the set of accepted types.
"""

from __future__ import annotations

import threading
import time
from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.steering.turns import TurnCoordinator


def _wait_until(pred, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return False


def test_already_running_when_same_type_in_flight():
    """running_key == dedup_key (the in-flight turn's type) => rejected, not queued."""
    c = TurnCoordinator()
    ran = []
    status = c.start_priority_async(
        lambda: ran.append(1), kind="manual_research",
        dedup_key="research", running_key="research")
    assert status == "already_running"
    # nothing was enqueued
    assert c.manual_waiting == 0
    assert c.queued_kinds() == []
    time.sleep(0.05)
    assert ran == []  # run_fn never invoked


def test_already_queued_when_same_type_waiting():
    """A second same-type trigger while the first holds the lock => already_queued."""
    c = TurnCoordinator()
    release = threading.Event()
    first = c.start_priority_async(
        lambda: release.wait(2), kind="manual_research",
        dedup_key="research", running_key=None)
    assert first == "started"
    assert _wait_until(lambda: "research" in c._pending_keys)

    # second same-type trigger: running_key=None so it can't match "already_running";
    # it is in _pending_keys => "already_queued".
    second = c.start_priority_async(
        lambda: None, kind="manual_research",
        dedup_key="research", running_key=None)
    assert second == "already_queued"

    release.set()
    assert _wait_until(lambda: c.manual_waiting == 0)
    assert c.queued_kinds() == []


def test_different_type_not_blocked():
    """A different turn type is queued normally even while another holds the lock."""
    c = TurnCoordinator()
    release = threading.Event()
    c.start_priority_async(lambda: release.wait(2), kind="manual_research",
                           dedup_key="research", running_key=None)
    assert _wait_until(lambda: "research" in c._pending_keys)

    other = c.start_priority_async(lambda: None, kind="manual_intraday",
                                   dedup_key="intraday", running_key="research")
    assert other == "queued"  # lock held by research => queued, not blocked
    assert "intraday" in c._pending_keys

    release.set()
    assert _wait_until(lambda: c.manual_waiting == 0)


def test_pending_cleared_after_completion_allows_requeue():
    """Once a turn finishes its key leaves _pending_keys, so it can be triggered again."""
    c = TurnCoordinator()
    s1 = c.start_priority_async(lambda: None, kind="manual_research",
                                dedup_key="research", running_key=None)
    assert s1 == "started"
    assert _wait_until(lambda: c.manual_waiting == 0)
    assert "research" not in c._pending_keys
    # same type again now succeeds (no longer running/queued)
    s2 = c.start_priority_async(lambda: None, kind="manual_research",
                                dedup_key="research", running_key=None)
    assert s2 == "started"
    assert _wait_until(lambda: c.manual_waiting == 0)


def test_queued_kinds_excludes_running():
    """queued_kinds(running_key) reports only WAITING kinds, not the in-flight one."""
    c = TurnCoordinator()
    release = threading.Event()
    c.start_priority_async(lambda: release.wait(2), kind="manual_research",
                           dedup_key="research", running_key=None)
    assert _wait_until(lambda: "research" in c._pending_keys)
    c.start_priority_async(lambda: release.wait(2), kind="manual_intraday",
                           dedup_key="intraday", running_key="research")
    assert _wait_until(lambda: "intraday" in c._pending_keys)

    # research is the in-flight turn; intraday is genuinely waiting.
    assert c.queued_kinds(running_key="research") == ["intraday"]
    # with no running key both are reported as pending.
    assert c.queued_kinds() == ["intraday", "research"]

    release.set()
    assert _wait_until(lambda: c.manual_waiting == 0)


def test_dedup_does_not_affect_non_dedup_callers():
    """Without dedup_key the legacy behavior (always enqueue) is preserved."""
    c = TurnCoordinator()
    release = threading.Event()
    a = c.start_priority_async(lambda: release.wait(2), kind="manual")
    b = c.start_priority_async(lambda: None, kind="manual")  # no dedup => queued, not rejected
    assert a == "started" and b == "queued"
    release.set()
    assert _wait_until(lambda: c.manual_waiting == 0)


@settings(max_examples=60, deadline=None)
@given(keys=st.lists(st.sampled_from(["research", "intraday", "eod"]),
                     min_size=1, max_size=12))
def test_property_no_duplicate_pending_per_type(keys):
    """Invariant: across any trigger sequence, at most ONE accepted (started/queued)
    entry exists per turn type; the rest are rejected; _pending_keys == accepted set."""
    c = TurnCoordinator()
    release = threading.Event()
    accepted: Counter[str] = Counter()
    try:
        for k in keys:
            # running_key=None so only the queued-dedup path is exercised (first per key
            # accepted, subsequent same-key rejected as already_queued).
            st_ = c.start_priority_async(lambda: release.wait(5), kind=f"manual_{k}",
                                         dedup_key=k, running_key=None, timeout=5)
            assert st_ in ("started", "queued", "already_queued")
            if st_ in ("started", "queued"):
                accepted[k] += 1
            else:
                assert k in c._pending_keys  # rejected because already pending

        # at most one accepted per distinct key
        assert all(cnt == 1 for cnt in accepted.values())
        # pending set is exactly the accepted (distinct) keys
        assert set(c._pending_keys) == set(accepted.keys())
    finally:
        release.set()
        assert _wait_until(lambda: c.manual_waiting == 0, timeout=6)
    # fully drained
    assert c.queued_kinds() == []
