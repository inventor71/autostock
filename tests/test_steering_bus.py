"""Unit A steering-core -- Step 5: CommandBus (single worker + emergency lane)."""

from __future__ import annotations

import threading
import time

import pytest

from src.agent.steering.bus import CommandBus


@pytest.fixture
def bus():
    b = CommandBus()
    b.start()
    yield b
    b.stop()


def test_result_value_and_exception(bus):
    assert bus.submit_and_wait(lambda: 21 * 2, timeout=2) == 42
    with pytest.raises(ValueError):
        bus.submit_and_wait(lambda: (_ for _ in ()).throw(ValueError("boom")), timeout=2)
    # worker survives the failed item
    assert bus.submit_and_wait(lambda: "alive", timeout=2) == "alive"


def test_single_threaded_serialization(bus):
    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def work():
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.01)
        with lock:
            active["n"] -= 1

    results = [bus.submit(work) for _ in range(20)]
    for r in results:
        r.wait(3)
    assert active["max"] == 1  # never two items running at once


def test_emergency_jumps_queued_normal(bus):
    order: list[str] = []
    gate = threading.Event()

    # occupy the worker so the next two items queue up behind it
    busy = bus.submit(lambda: gate.wait(2))
    # give the worker a moment to pick up the blocker
    time.sleep(0.05)
    rn = bus.submit(lambda: order.append("normal"))
    re = bus.submit(lambda: order.append("emergency"), emergency=True)
    assert bus.emergency_pending() is True
    gate.set()  # release the worker
    busy.wait(2); re.wait(2); rn.wait(2)
    assert order == ["emergency", "normal"]
    assert bus.emergency_pending() is False


def test_fifo_within_normal_lane(bus):
    order: list[int] = []
    gate = threading.Event()
    bus.submit(lambda: gate.wait(2))
    time.sleep(0.05)
    rs = [bus.submit(lambda i=i: order.append(i)) for i in range(5)]
    gate.set()
    for r in rs:
        r.wait(2)
    assert order == [0, 1, 2, 3, 4]
