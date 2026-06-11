"""F54 — short-selling tests (Unit A: Trading Core).

Covers the inverted risk geometry, mandatory-stop guard, auto-flip, dual circuit
breaker, direction-aware polled exits, and the short order path through the
simulated broker. Property-based tests (Hypothesis) assert the load-bearing
invariants: short P&L sign, short-stop ceiling, and Order JSON round-trip.
"""

from __future__ import annotations

import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision, Journal
from src.core.models import Order, PortfolioState, Position, TradeSignal
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide, Signal
from src.execution.brokers.simulated_broker import SimulatedBroker
from src.risk.manager import RiskManager


class _FakeDP:
    """Minimal data provider for the executor (fixed price, no bars)."""

    def __init__(self, price: float):
        self.price = price

    def get_latest_price(self, symbol: str) -> float:
        return self.price

    def get_bars(self, symbol: str, limit: int = 2):
        return None


def _pf(cash: float = 100_000.0, **positions: Position) -> PortfolioState:
    return PortfolioState(cash=cash, equity=cash, positions=dict(positions))


# --------------------------------------------------------------------------- #
# Position P&L direction (BR-13)
# --------------------------------------------------------------------------- #
class TestShortPnL:
    def test_short_profits_when_price_falls(self):
        p = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
        p.update_price(90)
        assert p.unrealized_pnl == pytest.approx(100)  # (100-90)*10

    def test_short_loses_when_price_rises(self):
        p = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
        p.update_price(110)
        assert p.unrealized_pnl == pytest.approx(-100)

    def test_long_unchanged(self):
        p = Position(symbol="X", qty=10, avg_entry_price=100)  # default LONG
        p.update_price(110)
        assert p.unrealized_pnl == pytest.approx(100)


# --------------------------------------------------------------------------- #
# Order bracket geometry (BR-2 / BR-14)
# --------------------------------------------------------------------------- #
class TestShortBracketGeometry:
    def test_valid_short_bracket(self):
        o = Order(
            symbol="X", side=OrderSide.SELL_SHORT, qty=10, limit_price=100,
            order_class=OrderClass.BRACKET, stop_loss_price=110, take_profit_price=85,
        )
        assert o.stop_loss_price > o.limit_price > o.take_profit_price

    def test_short_stop_below_entry_rejected(self):
        with pytest.raises(ValueError, match="stop_loss"):
            Order(
                symbol="X", side=OrderSide.SELL_SHORT, qty=10, limit_price=100,
                order_class=OrderClass.BRACKET, stop_loss_price=90, take_profit_price=85,
            )

    def test_short_target_above_entry_rejected(self):
        with pytest.raises(ValueError, match="take_profit"):
            Order(
                symbol="X", side=OrderSide.SELL_SHORT, qty=10, limit_price=100,
                order_class=OrderClass.BRACKET, stop_loss_price=110, take_profit_price=105,
            )

    def test_long_bracket_still_validated(self):
        with pytest.raises(ValueError):
            Order(
                symbol="X", side=OrderSide.BUY, qty=10, limit_price=100,
                order_class=OrderClass.BRACKET, stop_loss_price=110, take_profit_price=120,
            )

    def test_market_short_bracket_misoriented_stop_rejected(self):
        """critic #4: a MARKET short bracket (limit_price=None) must still reject
        a stop that sits below the take-profit (mis-oriented)."""
        with pytest.raises(ValueError, match="stop_loss"):
            Order(
                symbol="X", side=OrderSide.SELL_SHORT, qty=10,  # no limit_price
                order_class=OrderClass.BRACKET, stop_loss_price=80, take_profit_price=120,
            )

    def test_market_short_bracket_correct_legs_ok(self):
        o = Order(
            symbol="X", side=OrderSide.SELL_SHORT, qty=10,  # market
            order_class=OrderClass.BRACKET, stop_loss_price=110, take_profit_price=85,
        )
        assert o.stop_loss_price > o.take_profit_price

    def test_market_long_bracket_misoriented_stop_rejected(self):
        with pytest.raises(ValueError, match="stop_loss"):
            Order(
                symbol="X", side=OrderSide.BUY, qty=10,  # market, no limit
                order_class=OrderClass.BRACKET, stop_loss_price=120, take_profit_price=80,
            )


# --------------------------------------------------------------------------- #
# Mandatory stop (BR-1)
# --------------------------------------------------------------------------- #
class TestMandatoryStop:
    def test_short_with_stop_accepted(self):
        rm = RiskManager(use_bracket_orders=True)
        sig = TradeSignal(
            symbol="X", signal=Signal.SELL_SHORT, confidence=0.7,
            metadata={"key_levels": {"entry": 100, "stop_loss": 108, "take_profit": 85}},
        )
        order = rm.evaluate_signal(sig, 100, _pf())
        assert order is not None and order.side == OrderSide.SELL_SHORT
        assert order.stop_loss_price > 100

    def test_short_without_stop_rejected(self):
        rm = RiskManager(use_bracket_orders=True)
        sig = TradeSignal(
            symbol="X", signal=Signal.SELL_SHORT, confidence=0.7,
            metadata={"key_levels": {}},  # no stop, no atr
        )
        assert rm.evaluate_signal(sig, 100, _pf()) is None

    def test_short_atr_fallback_stop(self):
        rm = RiskManager(use_bracket_orders=True)
        sig = TradeSignal(
            symbol="X", signal=Signal.SELL_SHORT, confidence=0.7,
            metadata={"key_levels": {}, "atr": 2.0},
        )
        order = rm.evaluate_signal(sig, 100, _pf())
        assert order is not None and order.stop_loss_price > 100

    def test_human_short_without_stop_rejected_even_with_force(self):
        rm = RiskManager(use_bracket_orders=True)
        order = Order(symbol="X", side=OrderSide.SELL_SHORT, qty=10)  # no legs
        # No ATR → auto-protect can't resolve a stop → NO_STOP, force can't override.
        dec = rm.receive_human_order(order, _pf(), price=100, atr=None, force=True)
        assert not dec.accepted and dec.reason_code == "NO_STOP"


# --------------------------------------------------------------------------- #
# Cover (BR-5)
# --------------------------------------------------------------------------- #
class TestCover:
    def test_full_cover(self):
        rm = RiskManager(use_bracket_orders=True)
        pf = _pf(positions={}, **{}) if False else PortfolioState(
            cash=100_000, equity=100_000,
            positions={"X": Position(symbol="X", qty=50, avg_entry_price=100, side=PositionSide.SHORT)},
        )
        order = rm.evaluate_signal(
            TradeSignal(symbol="X", signal=Signal.BUY_TO_COVER, sell_pct=1.0), 95, pf
        )
        assert order.side == OrderSide.BUY_TO_COVER and order.qty == 50

    def test_partial_cover(self):
        rm = RiskManager(use_bracket_orders=True)
        pf = PortfolioState(
            cash=100_000, equity=100_000,
            positions={"X": Position(symbol="X", qty=50, avg_entry_price=100, side=PositionSide.SHORT)},
        )
        order = rm.evaluate_signal(
            TradeSignal(symbol="X", signal=Signal.BUY_TO_COVER, sell_pct=0.4), 95, pf
        )
        assert order.qty == pytest.approx(20)

    def test_cover_without_short_position_skipped(self):
        rm = RiskManager(use_bracket_orders=True)
        assert rm.evaluate_signal(
            TradeSignal(symbol="X", signal=Signal.BUY_TO_COVER), 95, _pf()
        ) is None


# --------------------------------------------------------------------------- #
# Stop ratchet (BR-4)
# --------------------------------------------------------------------------- #
class TestShortRatchet:
    def test_short_stop_tightens_downward(self):
        rm = RiskManager()
        assert rm.ratchet_stop(108, 105, position_side=PositionSide.SHORT) == 105

    def test_short_stop_not_widened(self):
        rm = RiskManager()
        assert rm.ratchet_stop(108, 110, position_side=PositionSide.SHORT) == 108

    def test_long_stop_still_tightens_upward(self):
        rm = RiskManager()
        assert rm.ratchet_stop(95, 98) == 98
        assert rm.ratchet_stop(95, 92) == 95


# --------------------------------------------------------------------------- #
# Circuit breakers (BR-7)
# --------------------------------------------------------------------------- #
class TestDualCircuitBreaker:
    def test_market_drop_halts_buys_not_shorts(self):
        rm = RiskManager()
        rm.update_market_halt(-0.05)
        assert rm.new_buys_halted is True
        assert rm.new_shorts_halted is False

    def test_market_rally_halts_shorts_not_buys(self):
        rm = RiskManager()
        rm.update_market_halt(0.05)
        assert rm.new_shorts_halted is True
        assert rm.new_buys_halted is False

    def test_short_blocked_when_shorts_halted(self):
        rm = RiskManager(use_bracket_orders=True)
        rm.update_market_halt(0.05)  # halt shorts
        sig = TradeSignal(
            symbol="X", signal=Signal.SELL_SHORT,
            metadata={"key_levels": {"entry": 100, "stop_loss": 108}},
        )
        assert rm.evaluate_signal(sig, 100, _pf()) is None

    def test_individual_stock_squeeze_guard(self):
        rm = RiskManager(use_bracket_orders=True, individual_stock_halt_pct=0.10)
        sig = TradeSignal(
            symbol="X", signal=Signal.SELL_SHORT,
            metadata={"key_levels": {"entry": 100, "stop_loss": 108}, "prev_close": 88},
        )
        # price 100 vs prev_close 88 = +13.6% > 10% → reject
        assert rm.evaluate_signal(sig, 100, _pf()) is None


# --------------------------------------------------------------------------- #
# Polled exits direction (BR-11)
# --------------------------------------------------------------------------- #
class TestPolledExitsShort:
    def test_short_stop_loss_triggers_cover(self):
        rm = RiskManager(stop_loss_pct=0.05)
        pos = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
        pos.update_price(106)  # up 6% → short loss > 5%
        orders = rm.check_stop_loss(PortfolioState(cash=0, equity=0, positions={"X": pos}))
        assert len(orders) == 1 and orders[0].side == OrderSide.BUY_TO_COVER

    def test_short_take_profit_triggers_cover(self):
        rm = RiskManager(take_profit_pct=0.15)
        pos = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
        pos.update_price(80)  # down 20% → short gain > 15%
        orders = rm.check_take_profit(PortfolioState(cash=0, equity=0, positions={"X": pos}))
        assert len(orders) == 1 and orders[0].side == OrderSide.BUY_TO_COVER

    def test_long_polled_exits_unchanged(self):
        rm = RiskManager(stop_loss_pct=0.05)
        pos = Position(symbol="X", qty=10, avg_entry_price=100)  # LONG
        pos.update_price(94)
        orders = rm.check_stop_loss(PortfolioState(cash=0, equity=0, positions={"X": pos}))
        assert len(orders) == 1 and orders[0].side == OrderSide.SELL


# --------------------------------------------------------------------------- #
# Auto-flip (BR-6) via the executor + simulated broker
# --------------------------------------------------------------------------- #
class TestAutoFlip:
    def _executor(self, broker, price=100):
        rm = RiskManager(use_bracket_orders=True)
        return DecisionExecutor(
            broker, rm, _FakeDP(price),
            journal=Journal(root=tempfile.mkdtemp()), universe=["AAPL"],
        )

    def test_long_to_short_flip(self):
        broker = SimulatedBroker(initial_capital=100_000)
        broker.set_current_price("AAPL", 100)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=100))
        ex = self._executor(broker)
        out = ex.execute_decision(
            Decision(symbol="AAPL", action="SELL_SHORT", stop=108, target=85, confidence=0.7)
        )
        assert out.status == "executed"
        pos = broker.get_position("AAPL")
        assert pos is not None and pos.side == PositionSide.SHORT

    def test_short_to_long_flip(self):
        broker = SimulatedBroker(initial_capital=100_000)
        broker.set_current_price("AAPL", 100)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.SELL_SHORT, qty=100))
        ex = self._executor(broker)
        out = ex.execute_decision(
            Decision(symbol="AAPL", action="BUY", stop=92, target=120, confidence=0.7)
        )
        assert out.status == "executed"
        pos = broker.get_position("AAPL")
        assert pos is not None and pos.side == PositionSide.LONG

    def test_no_flip_when_same_direction(self):
        broker = SimulatedBroker(initial_capital=100_000)
        broker.set_current_price("AAPL", 100)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=100))
        ex = self._executor(broker)
        # BUY over an existing long → no flip; RiskManager skips ("already held")
        out = ex.execute_decision(
            Decision(symbol="AAPL", action="BUY", stop=92, target=120)
        )
        assert out.status == "no_order"
        assert broker.get_position("AAPL").side == PositionSide.LONG

    def test_flip_aborts_when_close_not_flat(self):
        """critic #1: if the close doesn't leave the position flat (async/partial),
        the flip must abort and NOT open the opposite side."""
        broker = SimulatedBroker(initial_capital=100_000)
        broker.set_current_price("AAPL", 100)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=100))
        long_pos = broker.get_position("AAPL")

        # Simulate a broker whose close_position reports a fill but leaves the
        # position un-flat (the exact AlpacaBroker qty-fallback hazard).
        def _fake_close(symbol):
            from src.core.models import FilledOrder
            from datetime import datetime
            return FilledOrder(
                order_id="pending-1", symbol=symbol, side=OrderSide.SELL,
                qty=100, filled_price=0.0, filled_at=datetime.now(),
            )
        broker.close_position = _fake_close  # type: ignore[method-assign]

        ex = self._executor(broker)
        out = ex.execute_decision(
            Decision(symbol="AAPL", action="SELL_SHORT", stop=108, target=85)
        )
        assert out.status == "error"
        # Still long — no short was opened on top of the unclosed long.
        assert broker.get_position("AAPL").side == PositionSide.LONG


class TestSqueezeGuardWired:
    """critic #3: prev_close must be populated so the guard actually fires."""

    class _DP:
        def __init__(self, price, prev):
            import pandas as pd
            self._price, self._bars = price, pd.DataFrame({"close": [prev, price]})

        def get_latest_price(self, s):
            return self._price

        def get_bars(self, s, limit=2):
            return self._bars

    def test_short_into_surging_stock_rejected_end_to_end(self):
        broker = SimulatedBroker(initial_capital=100_000)
        broker.set_current_price("AAPL", 100)
        rm = RiskManager(use_bracket_orders=True, individual_stock_halt_pct=0.10)
        dp = self._DP(price=100, prev=88)  # +13.6% on the day
        ex = DecisionExecutor(
            broker, rm, dp, journal=Journal(root=tempfile.mkdtemp()), universe=["AAPL"]
        )
        out = ex.execute_decision(
            Decision(symbol="AAPL", action="SELL_SHORT", stop=108, target=85)
        )
        assert out.status == "no_order"
        assert broker.get_position("AAPL") is None

    def test_short_into_calm_stock_allowed(self):
        broker = SimulatedBroker(initial_capital=100_000)
        broker.set_current_price("AAPL", 100)
        rm = RiskManager(use_bracket_orders=True, individual_stock_halt_pct=0.10)
        dp = self._DP(price=100, prev=99)  # +1% on the day
        ex = DecisionExecutor(
            broker, rm, dp, journal=Journal(root=tempfile.mkdtemp()), universe=["AAPL"]
        )
        out = ex.execute_decision(
            Decision(symbol="AAPL", action="SELL_SHORT", stop=108, target=85)
        )
        assert out.status == "executed"
        assert broker.get_position("AAPL").side == PositionSide.SHORT


# --------------------------------------------------------------------------- #
# Simulated broker short path
# --------------------------------------------------------------------------- #
class TestSimulatedBrokerShort:
    def test_short_open_and_cover_realizes_pnl(self):
        b = SimulatedBroker(initial_capital=100_000)
        b.set_current_price("X", 100)
        b.submit_order(Order(symbol="X", side=OrderSide.SELL_SHORT, qty=50))
        assert b.get_position("X").side == PositionSide.SHORT
        b.set_current_price("X", 90)
        b.submit_order(Order(symbol="X", side=OrderSide.BUY_TO_COVER, qty=50))
        assert b.get_position("X") is None
        # profit = 50 * (100 - 90) = 500
        assert b.get_portfolio_state().cash == pytest.approx(100_500)

    def test_short_equity_reflects_liability(self):
        b = SimulatedBroker(initial_capital=100_000)
        b.set_current_price("X", 100)
        b.submit_order(Order(symbol="X", side=OrderSide.SELL_SHORT, qty=50))
        b.set_current_price("X", 110)  # short underwater
        assert b.get_portfolio_state().equity == pytest.approx(99_500)

    def test_short_bracket_stop_covers(self):
        b = SimulatedBroker(initial_capital=100_000)
        b.set_current_price("Y", 100)
        b.submit_order(Order(
            symbol="Y", side=OrderSide.SELL_SHORT, qty=10, order_class=OrderClass.BRACKET,
            stop_loss_price=110, take_profit_price=85,
        ))
        # price rips up through the stop → bracket covers
        b.set_current_price("Y", 111, high=111, low=100)
        assert b.get_position("Y") is None

    def test_cannot_short_while_long(self):
        b = SimulatedBroker(initial_capital=100_000)
        b.set_current_price("X", 100)
        b.submit_order(Order(symbol="X", side=OrderSide.BUY, qty=10))
        with pytest.raises(Exception):
            b.submit_order(Order(symbol="X", side=OrderSide.SELL_SHORT, qty=10))


# --------------------------------------------------------------------------- #
# Property-based invariants (PBT-02 round-trip, PBT-03 invariants)
# --------------------------------------------------------------------------- #
class TestShortInvariants:
    @given(
        entry=st.floats(min_value=1, max_value=1000),
        price=st.floats(min_value=0.01, max_value=2000),
        qty=st.floats(min_value=0.001, max_value=1000),
    )
    @settings(max_examples=200)
    def test_short_pnl_sign_invariant(self, entry, price, qty):
        """For a short, P&L is positive iff price < entry (and vice versa)."""
        p = Position(symbol="X", qty=qty, avg_entry_price=entry, side=PositionSide.SHORT)
        p.update_price(price)
        if price < entry:
            assert p.unrealized_pnl >= 0
        elif price > entry:
            assert p.unrealized_pnl <= 0

    @given(
        entry=st.floats(min_value=1, max_value=500),
        stop=st.floats(min_value=0.01, max_value=2000),
    )
    @settings(max_examples=200)
    def test_short_stop_above_entry_or_none(self, entry, stop):
        """A resolved short stop is always strictly above entry, or None."""
        rm = RiskManager(use_bracket_orders=True)
        resolved = rm._resolve_short_stop(entry, stop, None)
        assert resolved is None or resolved > entry

    @given(
        entry=st.floats(min_value=1, max_value=500),
        atr=st.floats(min_value=0.01, max_value=50),
    )
    @settings(max_examples=100)
    def test_short_stop_respects_ceiling(self, entry, atr):
        """An ATR-derived short stop never exceeds the max-distance ceiling."""
        rm = RiskManager(use_bracket_orders=True, short_max_stop_distance_pct=0.12)
        resolved = rm._resolve_short_stop(entry, None, atr)
        if resolved is not None:
            assert resolved <= entry * 1.12 + 1e-6

    @given(
        qty=st.floats(min_value=0.001, max_value=1000),
        stop=st.floats(min_value=101, max_value=200),
        target=st.floats(min_value=1, max_value=99),
    )
    @settings(max_examples=100)
    def test_short_order_json_round_trip(self, qty, stop, target):
        """An Order with short legs survives JSON serialize → deserialize."""
        o = Order(
            symbol="X", side=OrderSide.SELL_SHORT, qty=qty, limit_price=100,
            order_class=OrderClass.BRACKET, stop_loss_price=stop, take_profit_price=target,
        )
        restored = Order.model_validate_json(o.model_dump_json())
        assert restored == o

    @given(action=st.sampled_from(["SELL_SHORT", "BUY_TO_COVER"]))
    @settings(max_examples=20)
    def test_decision_short_action_round_trip(self, action):
        """A Decision with a short action survives JSON round-trip."""
        d = Decision(symbol="X", action=action, stop=110, target=85)
        restored = Decision.model_validate_json(d.model_dump_json())
        assert restored.action == action
        assert restored.symbol == "X"
