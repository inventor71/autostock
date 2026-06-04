"""F60 — easy-to-borrow (ETB) gate: shorts limited to liquid, easy-to-borrow names.

The gate lives at the executor (agent path) and command handler (human path),
BEFORE RiskManager — broker.is_shortable() is the authority, fail-closed.
"""

from __future__ import annotations

import tempfile

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision, Journal
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler
from src.agent.steering.records import SteeringCommand, SteeringEvent
from src.agent.steering.state import SteeringState
from src.core.models import Order
from src.core.types import OrderSide, PositionSide
from src.execution.base import BaseBroker
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager

TOKEN = "tok"


class _DP:
    def get_latest_price(self, s):
        return 100.0

    def get_bars(self, s, limit=2):
        return None


class _NoBorrow(SimulatedBroker):
    """Simulated broker that reports nothing as easy-to-borrow."""

    def is_shortable(self, symbol):
        return False


def test_base_broker_default_is_permissive():
    # Simulated/backtest have no borrow concept → default True (tests unaffected).
    assert SimulatedBroker(initial_capital=1000).is_shortable("AAPL") is True
    assert BaseBroker.is_shortable.__doc__  # documented capability


def _executor(broker):
    return DecisionExecutor(
        broker, RiskManager(use_bracket_orders=True), _DP(),
        journal=Journal(root=tempfile.mkdtemp()), universe=["XYZ"],
    )


def test_agent_short_rejected_when_not_etb():
    b = _NoBorrow(initial_capital=100_000)
    b.set_current_price("XYZ", 100)
    out = _executor(b).execute_decision(Decision(symbol="XYZ", action="SELL_SHORT", stop=108, target=85))
    assert out.status == "skipped_not_shortable"
    assert b.get_position("XYZ") is None


def test_agent_short_allowed_when_etb():
    b = SimulatedBroker(initial_capital=100_000)  # permissive
    b.set_current_price("XYZ", 100)
    out = _executor(b).execute_decision(Decision(symbol="XYZ", action="SELL_SHORT", stop=108, target=85))
    assert out.status == "executed"
    assert b.get_position("XYZ").side == PositionSide.SHORT


def test_etb_gate_blocks_flip_before_closing_long():
    """A long→short flip must NOT close the long if the short can't be opened
    (non-ETB) — the ETB gate runs before _maybe_flip."""
    b = _NoBorrow(initial_capital=100_000)
    b.set_current_price("XYZ", 100)
    b.submit_order(Order(symbol="XYZ", side=OrderSide.BUY, qty=10))  # seed a long
    out = _executor(b).execute_decision(Decision(symbol="XYZ", action="SELL_SHORT", stop=108, target=85))
    assert out.status == "skipped_not_shortable"
    # long is untouched — the flip never closed it
    assert b.get_position("XYZ").side == PositionSide.LONG


def test_skipped_not_shortable_is_terminal_cursor_advances():
    """A non-ETB short is a permanent skip — the cursor advances past it (not retried)."""
    b = _NoBorrow(initial_capital=100_000)
    b.set_current_price("XYZ", 100)
    ex = _executor(b)
    j = ex.journal
    j.append_decision(Decision(symbol="XYZ", action="SELL_SHORT", stop=108, target=85))
    ex.execute_pending()
    cursor, _ = ex._load_cursor()
    assert cursor == 1  # advanced past the terminal skip
    # a second run does not re-process it
    assert ex.execute_pending() == []


# --- human path (command handler) ------------------------------------------ #
def _handler(tmp_path, broker):
    rm = RiskManager(use_bracket_orders=True)
    ex = DecisionExecutor(broker, rm, _DP(), journal=Journal(root=tmp_path / "ws"),
                          universe=["XYZ"])
    ex._atr = lambda s: 2.0
    state = SteeringState(tmp_path / "ws")
    channel = SteeringChannel(tmp_path / "steering", TOKEN)
    h = CommandHandler(channel, state, ex, reconcile_worker=None, reconcile_run_fn=None)
    return h, channel


def _last(channel):
    return SteeringEvent.model_validate_json(channel.events_file.read_text().splitlines()[-1])


def test_human_short_rejected_when_not_etb(tmp_path):
    b = _NoBorrow(initial_capital=100_000)
    b.set_current_price("XYZ", 100)
    h, channel = _handler(tmp_path, b)
    h.handle(SteeringCommand(verb="short", args={"symbol": "XYZ", "size": 1000.0, "unit": "$"},
                             confirmed=True, token=TOKEN))
    ev = _last(channel)
    assert ev.payload["outcome"] == "rejected" and "SHORTABLE" in ev.payload["detail"].upper()
    assert b.get_position("XYZ") is None


def test_human_short_allowed_when_etb(tmp_path):
    b = SimulatedBroker(initial_capital=100_000)  # permissive
    b.set_current_price("XYZ", 100)
    h, channel = _handler(tmp_path, b)
    h.handle(SteeringCommand(verb="short", args={"symbol": "XYZ", "size": 1000.0, "unit": "$"},
                             confirmed=True, token=TOKEN))
    assert _last(channel).payload["outcome"] == "executed"
    assert b.get_position("XYZ").side == PositionSide.SHORT
