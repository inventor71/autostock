"""Unit A steering-core -- Step 2: SteeringState (BR-3/BR-4) + ET-date + persistence."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.journal import Decision
from src.agent.steering import state as state_mod
from src.agent.steering.state import SteeringState


def _dec(symbol="AAPL", action="BUY", **kw):
    return Decision(symbol=symbol, action=action, **kw)


def test_run_state_set_and_persist_same_day(tmp_path):
    s = SteeringState(tmp_path)
    assert not s.run_state().paused
    s.set_paused(True)
    s.set_entries_halted(True)
    # reload same day -> restored (BR-3.3)
    s2 = SteeringState(tmp_path)
    assert s2.run_state().paused and s2.run_state().entries_halted


def test_run_state_resets_next_trading_day(tmp_path, monkeypatch):
    s = SteeringState(tmp_path)
    s.set_paused(True)
    # advance ET date -> reload should auto-reset to running
    monkeypatch.setattr(state_mod, "et_today", lambda: date(2099, 1, 2))
    s2 = SteeringState(tmp_path)
    assert not s2.run_state().paused


def test_lock_and_pending_approve_flow(tmp_path):
    s = SteeringState(tmp_path)
    s.lock_symbol("aapl")
    assert s.lock_status("AAPL") == "locked"
    pa = s.add_pending(_dec("AAPL", "BUY"))
    assert pa is not None and len(s.list_pending()) == 1
    approved = s.approve(pa.id)
    assert approved.status == "approved"
    assert approved.decision.symbol == "AAPL"
    assert s.lock_status("AAPL") is None  # approve unlocks (BR-4.3)


def test_two_rejections_deny_for_day(tmp_path):
    s = SteeringState(tmp_path)
    s.lock_symbol("MSFT")
    p1 = s.add_pending(_dec("MSFT", "SELL"))
    _, st1 = s.reject(p1.id, "no")
    assert st1 == "locked"  # 1st reject keeps lock
    p2 = s.add_pending(_dec("MSFT", "SELL", stop=10.0))  # different fingerprint
    _, st2 = s.reject(p2.id)
    assert st2 == "denied"  # 2nd reject -> denied (BR-4.4)
    assert s.lock_status("MSFT") == "denied"


def test_retrade_resets_denied(tmp_path):
    s = SteeringState(tmp_path)
    s.lock_symbol("NVDA")
    s.reject(s.add_pending(_dec("NVDA", "BUY")).id)
    s.reject(s.add_pending(_dec("NVDA", "BUY", stop=1.0)).id)
    assert s.lock_status("NVDA") == "denied"
    s.lock_symbol("NVDA")  # human re-trades -> reset (BR-4.11)
    assert s.lock_status("NVDA") == "locked"


def test_unlock_resolves_outstanding_pending(tmp_path):
    s = SteeringState(tmp_path)
    s.lock_symbol("TSLA")
    pa = s.add_pending(_dec("TSLA", "BUY"))
    resolved = s.unlock_symbol("TSLA")
    assert resolved == [pa.id]
    assert s.lock_status("TSLA") is None
    assert s.list_pending() == []  # no ghost entry (BR-4.10)


def test_add_pending_is_idempotent_on_fingerprint(tmp_path):
    s = SteeringState(tmp_path)
    s.lock_symbol("AAPL")
    d = _dec("AAPL", "BUY", stop=5.0)
    assert s.add_pending(d) is not None
    assert s.add_pending(_dec("AAPL", "BUY", stop=5.0)) is None  # same fp -> not double-parked
    assert len(s.list_pending()) == 1


def test_lock_lazy_expiry_next_day(tmp_path, monkeypatch):
    s = SteeringState(tmp_path)
    s.lock_symbol("AAPL")
    monkeypatch.setattr(state_mod, "et_today", lambda: date(2099, 6, 1))
    assert s.lock_status("AAPL") is None  # lazy-expired


def test_pending_decision_round_trips_faithfully(tmp_path):
    # critic #7: a parked decision must keep confidence (sizing) + valid_until.
    s = SteeringState(tmp_path)
    s.lock_symbol("AAPL")
    d = _dec("AAPL", "BUY", confidence=0.9, limit=200.0, stop=190.0, target=220.0)
    pa = s.add_pending(d)
    s2 = SteeringState(tmp_path)  # reload from disk
    loaded = {p.id: p for p in s2.list_pending()}[pa.id]
    assert loaded.decision.confidence == 0.9  # not defaulted to 0.5
    assert loaded.decision.limit == 200.0 and loaded.decision.stop == 190.0
    assert loaded.decision.source == "agent"


def test_approve_reject_ignore_past_day_pending(tmp_path, monkeypatch):
    # critic #3: approve/reject must agree with list_pending's date scope.
    s = SteeringState(tmp_path)
    s.lock_symbol("AAPL")
    pa = s.add_pending(_dec("AAPL", "BUY"))
    monkeypatch.setattr(state_mod, "et_today", lambda: date(2099, 1, 2))
    assert s.list_pending() == []          # hidden next day
    assert s.approve(pa.id) is None        # and not approvable
    assert s.reject(pa.id) == (None, None)  # nor rejectable


def test_directives(tmp_path):
    s = SteeringState(tmp_path)
    d = s.add_directive("be defensive")
    assert [x.text for x in s.active_directives()] == ["be defensive"]
    assert s.clear_directive("all") == 1
    assert s.active_directives() == []


def test_pending_counter_rehydrates_after_restart(tmp_path):
    s = SteeringState(tmp_path)
    s.lock_symbol("AAPL")
    p1 = s.add_pending(_dec("AAPL", "BUY"))
    s2 = SteeringState(tmp_path)  # restart
    s2.lock_symbol("MSFT")
    p2 = s2.add_pending(_dec("MSFT", "BUY"))
    assert p2.id > p1.id  # ids never collide after restart (critic #3)


# --- PBT-03: lock state-machine invariants (BR-4.9) ------------------------- #
@settings(max_examples=50)
@given(rejects=st.integers(min_value=0, max_value=5))
def test_reject_count_monotone_and_denied_iff_two(tmp_path_factory, rejects):
    s = SteeringState(tmp_path_factory.mktemp("st"))
    s.lock_symbol("AAPL")
    last_status = "locked"
    for i in range(rejects):
        pa = s.add_pending(_dec("AAPL", "BUY", stop=float(i + 1)))
        if pa is None:
            continue
        _, last_status = s.reject(pa.id)
    status = s.lock_status("AAPL")
    if rejects == 0:
        assert status == "locked"
    elif rejects == 1:
        assert status == "locked"
    else:
        assert status == "denied"  # >=2 rejects => denied (monotone, capped)
