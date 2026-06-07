"""Characterization tests for AlpacaBroker (R3 broker-dedup safety net).

These lock the *current* behavior of the AlpacaBroker methods that the R3 refactor
moves into the shared ``AlpacaShapedBroker`` base — the methods `test_execution.py`
did NOT already cover (`_build_request` per order type, side/TIF mapping, open-orders
leg flatten, dict fill parse, latest-prices, is_shortable, replace_order, lifecycle).
Before/after the extraction these must stay green (behavior-preserving / T1).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.exceptions import BrokerError
from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType, PositionSide
from src.execution.brokers.alpaca_broker import AlpacaBroker, TradingClient

pytestmark = pytest.mark.skipif(TradingClient is None, reason="alpaca-py not installed")


def _broker(**overrides):
    """AlpacaBroker with a MagicMock trading client (ctor does no network I/O)."""
    b = AlpacaBroker(api_key="x", secret_key="y", paper=True, **overrides)
    b._client = MagicMock()
    return b


def _req(broker, order: Order):
    return broker._build_request(order, broker._alpaca_side(order.side))


# ── side mapping (current correct behavior — preserved by AlpacaBroker._alpaca_side) ──

class TestSideMapping:
    def test_buy_and_cover_map_to_buy(self):
        b = _broker()
        assert str(b._alpaca_side(OrderSide.BUY)).endswith("BUY")
        assert str(b._alpaca_side(OrderSide.BUY_TO_COVER)).endswith("BUY")

    def test_sell_and_short_map_to_sell(self):
        b = _broker()
        assert str(b._alpaca_side(OrderSide.SELL)).endswith("SELL")
        assert str(b._alpaca_side(OrderSide.SELL_SHORT)).endswith("SELL")


# ── _time_in_force (F9 fail-closed) ──

class TestTimeInForce:
    @pytest.mark.parametrize("tif", ["day", "gtc", "ioc", "fok"])
    def test_supported_tifs(self, tif):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_type=OrderType.MARKET,
                  time_in_force=tif)
        assert b._time_in_force(o) is not None

    def test_unsupported_tif_raises(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_type=OrderType.MARKET,
                  time_in_force="opg")
        with pytest.raises(BrokerError, match="unsupported time_in_force"):
            b._time_in_force(o)

    def test_bracket_forces_gtc(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_class=OrderClass.BRACKET,
                  order_type=OrderType.MARKET, take_profit_price=11, stop_loss_price=9,
                  time_in_force="day")
        assert str(b._time_in_force(o)).endswith("GTC")


# ── _build_request per order type (request shape is what moves to the base) ──

class TestBuildRequest:
    def test_market(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=5, order_type=OrderType.MARKET)
        assert type(_req(b, o)).__name__ == "MarketOrderRequest"

    def test_limit(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=5, order_type=OrderType.LIMIT,
                  limit_price=100.0)
        r = _req(b, o)
        assert type(r).__name__ == "LimitOrderRequest"
        assert float(r.limit_price) == 100.0

    def test_stop(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.SELL, qty=5, order_type=OrderType.STOP,
                  stop_price=90.0)
        r = _req(b, o)
        assert type(r).__name__ == "StopOrderRequest"
        assert float(r.stop_price) == 90.0

    def test_stop_limit(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.SELL, qty=5, order_type=OrderType.STOP_LIMIT,
                  stop_price=90.0, limit_price=89.0)
        r = _req(b, o)
        assert type(r).__name__ == "StopLimitOrderRequest"

    def test_trailing_stop_price(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.SELL, qty=5,
                  order_type=OrderType.TRAILING_STOP, trail_price=2.5)
        r = _req(b, o)
        assert type(r).__name__ == "TrailingStopOrderRequest"

    def test_bracket_market_entry(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=5, order_class=OrderClass.BRACKET,
                  order_type=OrderType.MARKET, take_profit_price=120, stop_loss_price=90)
        r = _req(b, o)
        assert type(r).__name__ == "MarketOrderRequest"
        assert str(r.order_class).endswith("BRACKET")

    def test_bracket_limit_entry(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=5, order_class=OrderClass.BRACKET,
                  order_type=OrderType.LIMIT, limit_price=100, take_profit_price=120,
                  stop_loss_price=90)
        r = _req(b, o)
        assert type(r).__name__ == "LimitOrderRequest"
        assert str(r.order_class).endswith("BRACKET")

    def test_oco(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.SELL, qty=5, order_class=OrderClass.OCO,
                  order_type=OrderType.LIMIT, take_profit_price=120, stop_loss_price=90)
        r = _req(b, o)
        assert type(r).__name__ == "LimitOrderRequest"
        assert str(r.order_class).endswith("OCO")

    def test_extras_extended_hours_and_client_id(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=5, order_type=OrderType.LIMIT,
                  limit_price=100.0, extended_hours=True, client_order_id="abc")
        r = _req(b, o)
        assert r.extended_hours is True
        assert r.client_order_id == "abc"

    def test_unsupported_order_type_raises(self):
        b = _broker()
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=5, order_type=OrderType.MARKET)
        # Force an unknown type past validation to hit the final raise.
        object.__setattr__(o, "order_type", "weird")
        with pytest.raises(BrokerError, match="Unsupported order type"):
            b._build_request(o, b._alpaca_side(OrderSide.BUY))


# ── submit_order / lifecycle ──

class TestSubmitAndLifecycle:
    def test_market_buy_fills(self):
        b = _broker()
        fake = SimpleNamespace(id="o1", status="filled", filled_avg_price=150.0,
                               filled_qty=10, filled_at=None, side="buy", symbol="AAPL",
                               qty=10)
        b._client.submit_order.return_value = fake
        b._client.get_order_by_id.return_value = fake
        filled = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10,
                                      order_type=OrderType.MARKET))
        assert filled.filled_price == 150.0 and filled.qty == 10
        b._client.submit_order.assert_called_once()

    def test_submit_failure_raises(self):
        b = _broker()
        b._client.submit_order.side_effect = RuntimeError("boom")
        with pytest.raises(BrokerError, match="Order submission failed"):
            b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1))

    def test_get_order_status_none_on_error(self):
        b = _broker()
        b._client.get_order_by_id.side_effect = RuntimeError("gone")
        assert b.get_order_status("x") is None

    def test_cancel_order_bool(self):
        b = _broker()
        assert b.cancel_order("o1") is True
        b._client.cancel_order_by_id.side_effect = RuntimeError("no")
        assert b.cancel_order("o1") is False

    def test_close_position(self):
        b = _broker()
        fake = SimpleNamespace(id="c1", status="filled", filled_avg_price=10.0,
                               filled_qty=3, filled_at=None, qty=3)
        b._client.close_position.return_value = fake
        b._client.get_order_by_id.return_value = fake
        filled = b.close_position("AAPL")
        assert filled is not None and filled.side == OrderSide.SELL


# ── positions / portfolio ──

class TestPositions:
    def _pos(self, side="long", qty=10):
        return SimpleNamespace(symbol="AAPL", qty=qty, side=side, avg_entry_price=100.0,
                               current_price=110.0, unrealized_pl=100.0, market_value=1100.0)

    def test_get_position_normalizes_qty(self):
        b = _broker()
        b._client.get_open_position.return_value = self._pos(side="short", qty=-10)
        p = b.get_position("AAPL")
        assert p.qty == 10 and p.side == PositionSide.SHORT

    def test_get_position_none_on_miss(self):
        b = _broker()
        b._client.get_open_position.side_effect = RuntimeError("none")
        assert b.get_position("AAPL") is None

    def test_portfolio_state(self):
        b = _broker()
        b._client.get_account.return_value = SimpleNamespace(cash="1000", equity="2000")
        b._client.get_all_positions.return_value = [self._pos()]
        ps = b.get_portfolio_state()
        assert ps.cash == 1000.0 and ps.equity == 2000.0 and "AAPL" in ps.positions


# ── open orders (leg flatten) ──

class TestOpenOrders:
    def test_flatten_legs_dedup(self):
        b = _broker()
        leg = SimpleNamespace(id="leg1", symbol="AAPL", side="sell", order_type="stop",
                              qty=10, limit_price=None, stop_price=90.0)
        parent = SimpleNamespace(id="p1", symbol="AAPL", side="buy", order_type="limit",
                                 qty=10, limit_price=120.0, stop_price=None, legs=[leg])
        b._client.get_orders.return_value = [parent]
        out = b.get_open_orders()
        ids = {o.order_id for o in out}
        assert ids == {"p1", "leg1"}

    def test_empty_on_failure(self):
        b = _broker()
        b._client.get_orders.side_effect = RuntimeError("x")
        assert b.get_open_orders() == []


# ── fills (raw dict parse) ──

class TestFills:
    def test_parse_dict_activity(self):
        b = _broker()
        b._client.get.return_value = [
            {"id": "f1", "symbol": "AAPL", "side": "buy", "qty": "5", "price": "100.0",
             "transaction_time": "2026-06-01T14:30:00Z"},
        ]
        fills = b.get_fills()
        assert len(fills) == 1 and fills[0].symbol == "AAPL" and fills[0].qty == 5.0

    def test_skips_non_buy_sell(self):
        b = _broker()
        b._client.get.return_value = [{"id": "f2", "symbol": "AAPL", "side": "x"}]
        assert b.get_fills() == []

    def test_best_effort_on_failure(self):
        b = _broker()
        b._client.get.side_effect = RuntimeError("down")
        assert b.get_fills() == []


# ── is_shortable (F60 fail-closed + cache) ──

class TestIsShortable:
    def test_true_when_all_flags(self):
        b = _broker()
        b._client.get_asset.return_value = SimpleNamespace(
            tradable=True, shortable=True, easy_to_borrow=True)
        assert b.is_shortable("AAPL") is True

    def test_false_when_missing_flag(self):
        b = _broker()
        b._client.get_asset.return_value = SimpleNamespace(
            tradable=True, shortable=True, easy_to_borrow=False)
        assert b.is_shortable("AAPL") is False

    def test_fail_closed_not_cached(self):
        b = _broker()
        b._client.get_asset.side_effect = RuntimeError("down")
        assert b.is_shortable("AAPL") is False
        assert "AAPL" not in b._etb_cache  # transient failure not cached


# ── replace_order ──

class TestReplaceOrder:
    def test_replace_returns_filled(self):
        b = _broker()
        settled = SimpleNamespace(id="r1", symbol="AAPL", side="buy", filled_qty=5,
                                  qty=5, filled_avg_price=100.0, filled_at=None,
                                  status="filled")
        b._client.replace_order_by_id.return_value = settled
        b._client.get_order_by_id.return_value = settled
        out = b.replace_order("o1", {"limit_price": 101.0})
        assert out is not None and out.order_id == "r1"

    def test_replace_none_on_failure(self):
        b = _broker()
        b._client.replace_order_by_id.side_effect = RuntimeError("x")
        assert b.replace_order("o1", {"qty": 2}) is None
