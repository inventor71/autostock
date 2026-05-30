"""Unit A steering-core -- Step 4: agent-decision human-approval gate (BR-4)."""

from __future__ import annotations

from src.agent.journal import Decision
from src.agent.steering.gate import gate_agent_decision
from src.agent.steering.state import SteeringState


def _state(tmp_path):
    return SteeringState(tmp_path)


def test_unlocked_symbol_executes(tmp_path):
    s = _state(tmp_path)
    res = gate_agent_decision(Decision(symbol="AAPL", action="BUY"), s)
    assert res.action == "execute"


def test_locked_symbol_parks(tmp_path):
    s = _state(tmp_path)
    s.lock_symbol("AAPL")
    res = gate_agent_decision(Decision(symbol="AAPL", action="SELL"), s)
    assert res.action == "park" and res.pending is not None
    assert len(s.list_pending()) == 1


def test_denied_symbol_auto_rejects(tmp_path):
    s = _state(tmp_path)
    s.lock_symbol("MSFT")
    s.reject(s.add_pending(Decision(symbol="MSFT", action="BUY")).id)
    s.reject(s.add_pending(Decision(symbol="MSFT", action="BUY", stop=9.0)).id)
    assert s.lock_status("MSFT") == "denied"
    res = gate_agent_decision(Decision(symbol="MSFT", action="BUY"), s)
    assert res.action == "deny" and res.pending is None


def test_protective_actions_never_gated(tmp_path):
    s = _state(tmp_path)
    s.lock_symbol("AAPL")  # even locked...
    for action in ("HOLD", "ADJUST_STOP"):
        res = gate_agent_decision(Decision(symbol="AAPL", action=action, stop=100.0), s)
        assert res.action == "execute", f"{action} must be exempt (BR-4.6)"
    # ...and no spurious pending was created by the protective path
    assert s.list_pending() == []
