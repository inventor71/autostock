"""F60 — easy-to-borrow (ETB) gate: shorts limited to liquid, easy-to-borrow names.

The gate lives at the executor (agent path) and command handler (human path),
BEFORE RiskManager — broker.is_shortable() is the authority, fail-closed.
Also covers code-review findings: SELL-on-SHORT guard, BrokerApiBroker parity.
"""

from __future__ import annotations

import tempfile

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision, Journal
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler
from src.agent.steering.records import SteeringCommand, SteeringEvent
from src.agent.steering.state import SteeringState
from src.core.models import Order, PortfolioState, Position, TradeSignal
from src.core.types import OrderSide, PositionSide, Signal
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


# --- SELL-on-SHORT guard (code-review finding) ---------------------------- #
def test_sell_on_short_position_rejected_by_risk_manager():
    """A SELL signal against a SHORT is rejected — prevents wrong-direction exit."""
    rm = RiskManager(use_bracket_orders=True)
    pos = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
    pf = PortfolioState(cash=100_000, equity=100_000, positions={"X": pos})
    sig = TradeSignal(symbol="X", signal=Signal.SELL)
    assert rm.evaluate_signal(sig, 100, pf) is None


def test_cover_on_short_position_accepted():
    """A BUY_TO_COVER against a SHORT is accepted (correct exit path)."""
    rm = RiskManager(use_bracket_orders=True)
    pos = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
    pf = PortfolioState(cash=100_000, equity=100_000, positions={"X": pos})
    sig = TradeSignal(symbol="X", signal=Signal.BUY_TO_COVER, sell_pct=1.0)
    order = rm.evaluate_signal(sig, 100, pf)
    assert order is not None and order.side == OrderSide.BUY_TO_COVER


def test_broker_api_broker_gets_side_from_f54_parity():
    """BrokerApiBroker.position_side mirrors AlpacaBroker (code-review finding #1).
    We test the static helper directly — it's shared across get_position/get_all_positions.
    This ensures a short held via broker_api is visible as SHORT, not defaulted to LONG."""
    from src.execution.brokers.broker_api_broker import BrokerApiBroker

    class _Pos:
        def __init__(self, side, qty):
            self.side = side
            self.qty = qty

    # Alpaca reports short with negative qty; side attribute may or may not be 'short'.
    assert BrokerApiBroker._position_side(_Pos("short", -100)) == PositionSide.SHORT
    assert BrokerApiBroker._position_side(_Pos("long", 100)) == PositionSide.LONG
    # Fallback via negative qty when side attribute is absent/ambiguous.
    assert BrokerApiBroker._position_side(_Pos("", -50)) == PositionSide.SHORT
    assert BrokerApiBroker._position_side(_Pos("", 50)) == PositionSide.LONG


# --- master short on/off toggle (F60) -------------------------------------- #
def test_config_ships_shorting_disabled():
    """Deployed default is OFF (opt-in) — the system trades long-only until enabled."""
    from config.config import RiskConfig
    assert RiskConfig().shorting_enabled is False


def test_disabled_rejects_agent_short():
    rm = RiskManager(use_bracket_orders=True, shorting_enabled=False)
    sig = TradeSignal(symbol="X", signal=Signal.SELL_SHORT,
                      metadata={"key_levels": {"entry": 100, "stop_loss": 108, "take_profit": 85}})
    assert rm.evaluate_signal(sig, 100, PortfolioState(cash=1e5, equity=1e5)) is None


def test_disabled_still_allows_cover_and_long():
    """Disabling shorts must NOT trap an existing short (cover works) or block longs."""
    rm = RiskManager(use_bracket_orders=True, shorting_enabled=False)
    pos = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
    pf = PortfolioState(cash=1e5, equity=1e5, positions={"X": pos})
    cover = rm.evaluate_signal(TradeSignal(symbol="X", signal=Signal.BUY_TO_COVER, sell_pct=1.0), 95, pf)
    assert cover is not None and cover.side == OrderSide.BUY_TO_COVER
    # a long entry on a different symbol is unaffected
    buy = rm.evaluate_signal(
        TradeSignal(symbol="Y", signal=Signal.BUY,
                    metadata={"key_levels": {"entry": 50, "stop_loss": 45, "take_profit": 70}}),
        50, PortfolioState(cash=1e5, equity=1e5))
    assert buy is not None and buy.side == OrderSide.BUY


def test_disabled_executor_skips_short_without_closing_long():
    """Master switch checked before auto-flip → a disabled short never flattens a long."""
    b = SimulatedBroker(initial_capital=100_000)
    b.set_current_price("XYZ", 100)
    b.submit_order(Order(symbol="XYZ", side=OrderSide.BUY, qty=10))
    rm = RiskManager(use_bracket_orders=True, shorting_enabled=False)
    ex = DecisionExecutor(b, rm, _DP(), journal=Journal(root=tempfile.mkdtemp()), universe=["XYZ"])
    out = ex.execute_decision(Decision(symbol="XYZ", action="SELL_SHORT", stop=108, target=85))
    assert out.status == "skipped_shorting_disabled"
    assert b.get_position("XYZ").side == PositionSide.LONG  # long untouched


def test_enabled_allows_short():
    rm = RiskManager(use_bracket_orders=True, shorting_enabled=True)
    sig = TradeSignal(symbol="X", signal=Signal.SELL_SHORT,
                      metadata={"key_levels": {"entry": 100, "stop_loss": 108, "take_profit": 85}})
    order = rm.evaluate_signal(sig, 100, PortfolioState(cash=1e5, equity=1e5))
    assert order is not None and order.side == OrderSide.SELL_SHORT


def test_prompt_omits_short_guidance_when_disabled():
    """When shorts are off, the research prompt must NOT instruct the agent to
    short — otherwise it wastes turns proposing rejected SELL_SHORTs."""
    from src.agent import prompts
    on = prompts.morning_research_prompt(["AAPL"], ["AAPL"], shorting_enabled=True)
    off = prompts.morning_research_prompt(["AAPL"], ["AAPL"], shorting_enabled=False)
    assert "SELL_SHORT" in on and "Short selling" in on
    assert "SELL_SHORT" not in off and "Short selling" not in off
    # multi-agent prompt too
    assert "SELL_SHORT" not in prompts.multi_research_initial_prompt(["AAPL"], shorting_enabled=False)
