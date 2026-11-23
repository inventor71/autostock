import copy
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.core.exceptions import BrokerError
from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.brokers.toss.broker import TossBroker


def broker_fixture(client_factory, examples, us_order, *, read_only=False, extra=None):
    row = copy.deepcopy(us_order)
    row.update(orderId="placed-order", side="BUY", status="PENDING")
    row["execution"].update(filledQuantity="0", averageFilledPrice=None, filledAt=None)

    def route(request):
        path = request.url.path
        if extra:
            result = extra(request)
            if result is not None:
                return result
        if path == "/api/v1/stocks":
            return [{"symbol": "AAPL", "currency": "USD", "status": "ACTIVE"}]
        if path == "/api/v1/market-calendar/US":
            now = datetime.now(UTC)
            return {"today": {"regularMarket": {
                "startTime": (now - timedelta(hours=1)).isoformat(),
                "endTime": (now + timedelta(hours=1)).isoformat(),
            }}}
        if path == "/api/v1/orders" and request.method == "POST":
            return {"orderId": "placed-order"}
        if path == "/api/v1/orders" and request.method == "GET":
            return examples["orders"]["result"]
        if path == "/api/v1/conditional-orders":
            return {"conditionalOrders": [], "hasNext": False, "nextCursor": None}
        if path == "/api/v1/holdings":
            return examples["holdings"]["result"]
        if path == "/api/v1/buying-power":
            return {"currency": "USD", "cashBuyingPower": "3500.50"}
        if path == "/api/v1/sellable-quantity":
            return {"sellableQuantity": "10"}
        if path.startswith("/api/v1/orders/"):
            return row
        raise AssertionError(f"Unexpected API path: {path}")

    client, calls = client_factory(route, read_only=read_only)
    broker = TossBroker(client, fill_poll_timeout=0)
    broker.cancel_settle_wait = 0
    return broker, calls, row


@pytest.fixture
def make_broker(client_factory, examples, us_order):
    return lambda **kw: broker_fixture(client_factory, examples, us_order, **kw)


def test_pending_acceptance_is_not_a_fill_and_preserves_id(make_broker):
    broker, calls, _ = make_broker()
    order = Order(symbol="AAPL", side=OrderSide.BUY, qty=2)
    result = broker.submit_order(order)
    assert result.order_id == "placed-order"
    assert result.qty == 0 and result.filled_price == 0
    posted = json.loads(next(r.content for r in calls if r.method == "POST" and r.url.path == "/api/v1/orders"))
    assert posted["clientOrderId"] == order.client_order_id
    assert posted["side"] == "BUY" and posted["orderType"] == "MARKET"
    assert posted["timeInForce"] == "DAY"
    assert "confirmHighValueOrder" not in posted


def test_partial_fill_uses_executed_quantity_not_requested(make_broker):
    broker, _, row = make_broker()
    row["execution"].update(filledQuantity="2", averageFilledPrice="185.25", commission="0.66", tax="0.1")
    row["status"] = "PARTIAL_FILLED"
    result = broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=5))
    assert result.qty == 2
    assert result.filled_price == 185.25
    assert result.commission == pytest.approx(0.76)


def test_read_failure_after_acceptance_preserves_pending_id(make_broker):
    def fail_read(r):
        if r.url.path == "/api/v1/orders/placed-order":
            return httpx.Response(403)

    broker, calls, _ = make_broker(extra=fail_read)
    result = broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=2))
    assert result.order_id == "placed-order" and result.qty == 0
    assert sum(r.method == "POST" and r.url.path == "/api/v1/orders" for r in calls) == 1


@pytest.mark.parametrize("kwargs", [
    {"order_class": OrderClass.BRACKET, "stop_loss_price": 90, "take_profit_price": 120},
    {"order_class": OrderClass.OCO, "stop_loss_price": 90, "take_profit_price": 120},
    {"order_class": OrderClass.OTO},
    {"order_type": OrderType.STOP, "stop_price": 90},
    {"order_type": OrderType.STOP_LIMIT, "stop_price": 90, "limit_price": 89},
    {"order_type": OrderType.TRAILING_STOP, "trail_percent": 2},
    {"side": OrderSide.SELL_SHORT}, {"side": OrderSide.BUY_TO_COVER},
    {"qty": 1.5}, {"qty": 0}, {"qty": -1}, {"qty": float("nan")}, {"qty": float("inf")},
    {"time_in_force": "gtc"}, {"extended_hours": True},
    {"order_type": OrderType.LIMIT, "limit_price": 1.001},
    {"order_type": OrderType.LIMIT, "limit_price": None},
    {"stop_loss_price": 90}, {"limit_price": 100}, {"client_order_id": "invalid id"},
])
def test_unsupported_orders_fail_before_any_network_call(make_broker, kwargs):
    broker, calls, _ = make_broker()
    order = Order(**{"symbol": "AAPL", "side": OrderSide.BUY, "qty": 1, **kwargs})
    with pytest.raises(BrokerError):
        broker.submit_order(order)
    assert calls == []


def test_read_only_broker_blocks_close_modify_cancel_and_submit(make_broker):
    broker, calls, _ = make_broker(read_only=True)
    actions = [
        lambda: broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1)),
        lambda: broker.close_position("AAPL"),
        lambda: broker.cancel_order("existing"),
        lambda: broker.replace_order("existing", {"limit_price": 100}),
    ]
    for action in actions:
        with pytest.raises(BrokerError, match="read-only"):
            action()
    assert calls == []


def test_sell_cannot_open_short_and_fractional_buy_is_rejected(make_broker):
    broker, calls, _ = make_broker()
    assert broker.is_shortable("AAPL") is False
    with pytest.raises(BrokerError, match="exceeds"):
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.SELL, qty=11))
    assert not any(r.method == "POST" and r.url.path == "/api/v1/orders" for r in calls)


def test_fractional_market_exit_supported(make_broker):
    broker, calls, _ = make_broker()
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.SELL, qty=0.123456))
    body = json.loads(next(r.content for r in calls if r.url.path == "/api/v1/orders" and r.method == "POST"))
    assert body["quantity"] == "0.123456"


def test_us_only_valuation_is_explicit_and_not_logged_as_returns(make_broker, tmp_path):
    from src.agent.logs.equity import record_equity
    from src.agent.tools.market import account
    broker, _, _ = make_broker(read_only=True)
    state = broker.get_portfolio_state()
    assert list(state.positions) == ["AAPL"]
    assert state.cash == 3500.5
    assert state.equity == pytest.approx(3500.5 + 1785)
    assert state.valuation_basis == "available_cash_plus_positions"
    assert state.currency == "USD"
    path = tmp_path / "equity.jsonl"
    with pytest.raises(ValueError, match="not account NAV"):
        record_equity(state, path)
    assert not path.exists()
    result = account(broker)
    assert result["valuation_basis"] == "available_cash_plus_positions"
    assert "Not account NAV" in result["valuation_note"]


def test_open_orders_are_scoped_to_us_and_remaining_quantity(make_broker):
    broker, _, _ = make_broker()
    opens = broker.get_open_orders()
    assert len(opens) == 1
    assert opens[0].symbol == "AAPL" and opens[0].qty == 3


def test_conditional_orders_cannot_be_hidden_before_close(make_broker, examples):
    conditional = copy.deepcopy(examples["conditional"]["result"])
    conditional["conditionalOrders"][0].update(market="US", symbol="AAPL")

    def extra(r):
        if r.url.path == "/api/v1/conditional-orders":
            return {**conditional, "hasNext": False, "nextCursor": None}

    broker, calls, _ = make_broker(extra=extra)
    with pytest.raises(BrokerError, match="conditional orders"):
        broker.close_position("AAPL")
    assert not any(r.method in {"POST", "DELETE"} and r.url.path != "/oauth2/token" for r in calls)


def test_cancel_ack_is_not_cancel_confirmation(make_broker):
    def extra(r):
        if r.url.path.endswith("/cancel"):
            return {"orderId": "cancel-operation-new-id"}

    broker, calls, _ = make_broker(extra=extra)
    assert broker.cancel_order("placed-order") is False
    assert calls[-1].url.path == "/api/v1/orders/placed-order"


def test_cancel_succeeds_only_when_original_is_canceled(make_broker):
    canceled = False
    holder = {}

    def extra(r):
        nonlocal canceled
        if r.url.path.endswith("/cancel"):
            canceled = True
            return {"orderId": "cancel-operation"}
        if canceled and r.url.path == "/api/v1/orders/placed-order":
            return {**holder["row"], "status": "CANCELED"}

    broker, _, row = make_broker(extra=extra)
    holder["row"] = row
    assert broker.cancel_order("placed-order") is True


def test_us_quantity_replacement_rejected_before_network(make_broker):
    broker, calls, _ = make_broker()
    with pytest.raises(BrokerError, match="quantity changes"):
        broker.replace_order("existing", {"qty": 2})
    assert calls == []


def test_modify_uses_new_operation_order_id(make_broker):
    def extra(r):
        if r.url.path.endswith("/modify"):
            assert json.loads(r.content) == {"orderType": "LIMIT", "price": "190.5"}
            return {"orderId": "replacement"}

    broker, calls, row = make_broker(extra=extra)
    row["orderId"] = "replacement"
    result = broker.replace_order("original", {"limit_price": 190.5})
    assert result.order_id == "replacement"
    assert calls[-1].url.path == "/api/v1/orders/replacement"


def test_us_holiday_is_closed(make_broker):
    broker, _, _ = make_broker(extra=lambda r: {"today": {"regularMarket": None}} if "market-calendar" in r.url.path else None)
    assert broker.is_market_open() is False


def test_accepted_modify_survives_read_failure(make_broker):
    def extra(r):
        if r.url.path.endswith("/modify"):
            return {"orderId": "replacement"}
        if r.url.path == "/api/v1/orders/replacement":
            return httpx.Response(403)

    broker, calls, _ = make_broker(extra=extra)
    result = broker.replace_order("original", {"limit_price": 190.5})
    assert result.order_id == "replacement" and result.qty == 0
    assert sum(r.url.path.endswith("/modify") for r in calls) == 1
