"""F9 U-RISK — Order model extensions, AlpacaBroker request mapping, and the
human-order reception gate (RiskManager.receive_human_order).

Covers FR-3 (param set + TIF fail-closed), FR-5/FR-5a (budget/pool/breaker +
force override), FR-6 (structured reject + suggestion), FR-7 boundaries, and
NFR-5 (Hypothesis property-based tests on the pure clamp/price-sanity logic).
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from src.core.models import Order, PortfolioState, Position
from src.core.types import OrderClass, OrderSide, OrderType
from src.risk.manager import OrderDecision, RiskManager


def _pf(cash=100_000.0, equity=100_000.0, positions=None):
    return PortfolioState(cash=cash, equity=equity, positions=positions or {})


def _pos(symbol="AAPL", qty=10.0, entry=100.0, price=100.0):
    return Position(symbol=symbol, qty=qty, avg_entry_price=entry, current_price=price)


# --------------------------------------------------------------------------- #
# Order model (C4)
# --------------------------------------------------------------------------- #
class TestOrderModel:
    def test_trailing_requires_exactly_one_trail(self):
        with pytest.raises(ValidationError):
            Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_type=OrderType.TRAILING_STOP)
        with pytest.raises(ValidationError):
            Order(symbol="AAPL", side=OrderSide.BUY, qty=1,
                  order_type=OrderType.TRAILING_STOP, trail_price=5, trail_percent=3)

    def test_trailing_price_or_percent_ok(self):
        a = Order(symbol="AAPL", side=OrderSide.BUY, qty=1,
                  order_type=OrderType.TRAILING_STOP, trail_price=5)
        b = Order(symbol="AAPL", side=OrderSide.BUY, qty=1,
                  order_type=OrderType.TRAILING_STOP, trail_percent=3)
        assert a.trail_price == 5 and b.trail_percent == 3

    def test_trail_only_on_trailing(self):
        with pytest.raises(ValidationError):
            Order(symbol="AAPL", side=OrderSide.BUY, qty=1, trail_price=5)

    def test_trail_percent_bounds(self):
        with pytest.raises(ValidationError):
            Order(symbol="AAPL", side=OrderSide.BUY, qty=1,
                  order_type=OrderType.TRAILING_STOP, trail_percent=150)

    def test_extras_default_safe(self):
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1)
        assert o.extended_hours is False and o.client_order_id is None


# --------------------------------------------------------------------------- #
# Broker request mapping (C6) — exercised without a live client.
# --------------------------------------------------------------------------- #
class TestBrokerMapping:
    @pytest.fixture
    def broker(self):
        ab = pytest.importorskip("src.execution.brokers.alpaca_broker")
        if ab.TradingClient is None:
            pytest.skip("alpaca-py not installed")
        return ab.AlpacaBroker.__new__(ab.AlpacaBroker), ab

    def _side(self, ab):
        from alpaca.trading.enums import OrderSide as AS
        return AS.BUY

    def test_unsupported_tif_rejected_not_downgraded(self, broker):
        b, ab = broker
        for bad in ("opg", "cls", "bogus"):
            o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1, time_in_force=bad)
            with pytest.raises(ab.BrokerError):
                b._time_in_force(o)

    def test_supported_tifs(self, broker):
        b, ab = broker
        from alpaca.trading.enums import TimeInForce
        got = {t: b._time_in_force(Order(symbol="A", side=OrderSide.BUY, qty=1, time_in_force=t))
               for t in ("day", "gtc", "ioc", "fok")}
        assert got["ioc"] == TimeInForce.IOC and got["fok"] == TimeInForce.FOK

    def test_trailing_request(self, broker):
        b, ab = broker
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=2,
                  order_type=OrderType.TRAILING_STOP, trail_percent=3)
        req = b._build_request(o, self._side(ab))
        assert type(req).__name__ == "TrailingStopOrderRequest"
        assert float(req.trail_percent) == 3.0

    def test_extras_passthrough(self, broker):
        b, ab = broker
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_type=OrderType.LIMIT,
                  limit_price=9, extended_hours=True, client_order_id="abc")
        req = b._build_request(o, self._side(ab))
        assert req.extended_hours is True and req.client_order_id == "abc"


# --------------------------------------------------------------------------- #
# Human-order gate (C5)
# --------------------------------------------------------------------------- #
class TestHumanOrderGate:
    def _rm(self):
        return RiskManager(use_bracket_orders=True)

    def test_capability_gate_not_overridable_by_force(self):
        rm = self._rm()
        d = rm.receive_human_order(
            Order(symbol="NVDA", side=OrderSide.BUY, qty=1, time_in_force="opg"),
            _pf(), price=100.0, force=True)
        assert not d.accepted and d.reason_code == "UNSUPPORTED_TIF"

    def test_oto_class_rejected(self):
        rm = self._rm()
        d = rm.receive_human_order(
            Order(symbol="NVDA", side=OrderSide.BUY, qty=1, order_class=OrderClass.OTO,
                  take_profit_price=120, stop_loss_price=90),
            _pf(), price=100.0)
        assert not d.accepted and d.reason_code == "UNSUPPORTED_CLASS"

    def test_breaker_blocks_then_force_passes(self):
        rm = self._rm()
        rm.update_market_halt(-0.05)
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=1), _pf(), 100.0)
        assert not d.accepted and d.reason_code == "BREAKER_HALTED" and d.suggestion == {"force": True}
        d2 = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=1), _pf(), 100.0, force=True)
        assert d2.accepted

    def test_pool_full_blocks(self):
        rm = self._rm()
        rm.max_open_positions = 1
        pf = _pf(positions={"AAPL": _pos("AAPL")})
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=1), pf, 100.0)
        assert not d.accepted and d.reason_code == "POOL_FULL"

    def test_no_add_to_existing(self):
        rm = self._rm()
        pf = _pf(positions={"AAPL": _pos("AAPL")})
        d = rm.receive_human_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1), pf, 100.0)
        assert not d.accepted and d.reason_code == "ALREADY_HELD"

    def test_clamp_with_suggestion(self):
        rm = self._rm()
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=10_000),
                                   _pf(cash=10_000, equity=10_000), 100.0)
        assert d.accepted and d.reason_code == "CLAMPED"
        assert d.order.qty < 10_000 and d.suggestion["qty"] == d.order.qty

    def test_force_skips_clamp(self):
        rm = self._rm()
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=10_000),
                                   _pf(cash=10_000, equity=10_000), 100.0, force=True)
        assert d.accepted and d.order.qty == 10_000

    def test_price_sanity_long_stop_above_entry(self):
        rm = self._rm()
        d = rm.receive_human_order(
            Order(symbol="NVDA", side=OrderSide.BUY, qty=1, order_class=OrderClass.BRACKET,
                  take_profit_price=120, stop_loss_price=110),  # stop above 100 mkt
            _pf(), price=100.0, force=True)
        assert not d.accepted and d.reason_code == "PRICE_SANITY"

    def test_autoprotect_attaches_bracket_with_atr(self):
        rm = self._rm()
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=1),
                                   _pf(), price=100.0, atr=2.0, force=True)
        assert d.accepted and d.order.order_class == OrderClass.BRACKET
        assert d.order.stop_loss_price is not None and d.order.take_profit_price is not None

    def test_no_autoprotect_without_stop_source(self):
        rm = self._rm()
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.BUY, qty=1),
                                   _pf(), price=100.0, force=True)  # no atr, no level
        assert d.accepted and d.order.order_class == OrderClass.SIMPLE

    def test_sell_requires_position(self):
        rm = self._rm()
        d = rm.receive_human_order(Order(symbol="NVDA", side=OrderSide.SELL, qty=1), _pf(), 100.0)
        assert not d.accepted and d.reason_code == "NO_POSITION"

    def test_sell_clamps_to_held(self):
        rm = self._rm()
        pf = _pf(positions={"AAPL": _pos("AAPL", qty=5)})
        d = rm.receive_human_order(Order(symbol="AAPL", side=OrderSide.SELL, qty=999), pf, 100.0)
        assert d.accepted and d.order.qty == 5 and d.reason_code == "CLAMPED"

    def test_sell_protective_stop_above_market_rejected(self):
        rm = self._rm()
        pf = _pf(positions={"AAPL": _pos("AAPL")})
        d = rm.receive_human_order(
            Order(symbol="AAPL", side=OrderSide.SELL, qty=1, order_type=OrderType.STOP, stop_price=110),
            pf, price=100.0)
        assert not d.accepted and d.reason_code == "PRICE_SANITY"


# --------------------------------------------------------------------------- #
# Property-based tests (NFR-5)
# --------------------------------------------------------------------------- #
class TestProperties:
    @settings(max_examples=200, deadline=None)
    @given(
        qty=st.integers(min_value=1, max_value=10_000),
        price=st.floats(min_value=1.0, max_value=5_000.0, allow_nan=False, allow_infinity=False),
        equity=st.floats(min_value=1_000.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False),
    )
    def test_buy_never_exceeds_request_and_is_protected_or_simple(self, qty, price, equity):
        """Without force, the accepted qty is never more than requested; a clamp
        always carries a suggestion; an accepted order is well-formed."""
        rm = RiskManager(use_bracket_orders=True)
        pf = _pf(cash=equity, equity=equity)
        d = rm.receive_human_order(Order(symbol="X", side=OrderSide.BUY, qty=qty), pf, price)
        if d.accepted:
            assert 0 < d.order.qty <= qty
            if d.order.qty != qty:
                assert d.reason_code == "CLAMPED" and d.suggestion["qty"] == d.order.qty
        else:
            # the only non-force rejects here are budget/zero-qty
            assert d.reason_code in {"NO_BUDGET", "ZERO_QTY"}

    @settings(max_examples=200, deadline=None)
    @given(
        held=st.floats(min_value=0.001, max_value=1_000.0, allow_nan=False, allow_infinity=False),
        req=st.integers(min_value=1, max_value=5_000),
    )
    def test_sell_never_oversells(self, held, req):
        rm = RiskManager()
        pf = _pf(positions={"S": _pos("S", qty=held)})
        d = rm.receive_human_order(Order(symbol="S", side=OrderSide.SELL, qty=req), pf, 100.0)
        assert d.accepted and d.order.qty <= held + 1e-9

    @settings(max_examples=100, deadline=None)
    @given(force=st.booleans())
    def test_unsupported_tif_always_rejected(self, force):
        rm = RiskManager()
        d = rm.receive_human_order(
            Order(symbol="X", side=OrderSide.BUY, qty=1, time_in_force="opg"),
            _pf(), 100.0, force=force)
        assert not d.accepted and d.reason_code == "UNSUPPORTED_TIF"
