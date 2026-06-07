from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import BrokerError
from src.core.models import FilledOrder, OpenOrder, Order, Position
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.brokers.broker_api_broker import (
    BrokerApiBroker,
    _LedgerClientShim,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _mock_broker_client():
    """Returns a fresh MagicMock standing in for BrokerClient."""
    return MagicMock()


def _fresh_impl(mock_broker=None, **overrides):
    """Create a BrokerApiBroker with a mocked BrokerClient.

    Patches get_trade_account_by_id so init validation never hits the network.
    """
    kwargs = dict(
        api_key="test-key",
        secret_key="test-secret",
        account_id="00000000-0000-0000-0000-000000000001",
    )
    kwargs.update(overrides)
    if mock_broker is None:
        mock_broker = MagicMock()
    impl = BrokerApiBroker.__new__(BrokerApiBroker)
    impl._c = mock_broker
    impl._account_id = str(kwargs["account_id"])
    impl._api_key = kwargs["api_key"]
    impl._secret_key = kwargs["secret_key"]
    impl._fill_poll_timeout = kwargs.get("fill_poll_timeout", 5.0)
    impl._fill_poll_interval = kwargs.get("fill_poll_interval", 0.2)
    impl._data_client = None
    impl._etb_cache = {}
    impl._etb_ttl = 1800.0
    # Mirror __init__: SDK request-envelope classes + open-orders query (R3 dedup
    # moved the shared algorithm to AlpacaShapedBroker, which reads these attrs).
    from alpaca.broker.requests import (
        MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest,
    )
    from alpaca.trading.enums import QueryOrderStatus
    impl._req_market = MarketOrderRequest
    impl._req_limit = LimitOrderRequest
    impl._req_stop = StopOrderRequest
    impl._req_stop_limit = StopLimitOrderRequest
    impl._req_trailing = None
    impl._open_orders_status = QueryOrderStatus.ALL
    acct = MagicMock()
    acct.account_number = "PA000001"
    impl._c.get_trade_account_by_id.return_value = acct
    impl._account_number = acct.account_number
    impl._masked_id = BrokerApiBroker._mask(impl._account_id)
    return impl


# ── fail-closed init ─────────────────────────────────────────────────────

class TestFailClosedInit:
    def test_missing_api_key(self):
        with pytest.raises(BrokerError, match="BROKER_API_KEY"):
            BrokerApiBroker(api_key="", secret_key="s", account_id="a")

    def test_missing_secret(self):
        with pytest.raises(BrokerError, match="BROKER_API_SECRET"):
            BrokerApiBroker(api_key="k", secret_key="", account_id="a")

    def test_missing_account_id(self):
        with pytest.raises(BrokerError, match="BROKER_ACCOUNT_ID"):
            BrokerApiBroker(api_key="k", secret_key="s", account_id="")

    def test_missing_client_import(self):
        from src.execution.brokers import broker_api_broker as m
        old = m.BrokerClient
        try:
            m.BrokerClient = None
            with pytest.raises(BrokerError, match="alpaca-py"):
                m.BrokerApiBroker(api_key="k", secret_key="s", account_id="a")
        finally:
            m.BrokerClient = old

    def test_valid_init_logs_masked_id(self):
        impl = _fresh_impl()
        assert impl._account_id == "00000000-0000-0000-0000-000000000001"
        assert len(impl._masked_id) == 9  # "00000000…"
        assert impl._masked_id.endswith("…")


# ── submit_order ─────────────────────────────────────────────────────────

class TestSubmitOrder:
    def test_market_buy(self):
        impl = _fresh_impl()
        fake_order = MagicMock()
        fake_order.id = "order-123"
        fake_order.status = "filled"
        fake_order.filled_avg_price = 150.0
        fake_order.filled_qty = 10
        fake_order.filled_at = None
        impl._c.submit_order_for_account.return_value = fake_order
        impl._c.get_order_for_account_by_id.return_value = fake_order

        order = Order(symbol="AAPL", side=OrderSide.BUY, qty=10, order_type=OrderType.MARKET)
        filled = impl.submit_order(order)
        assert filled.symbol == "AAPL"
        assert filled.qty == 10
        assert filled.filled_price == 150.0
        impl._c.submit_order_for_account.assert_called_once()

    def test_bracket_limit_entry(self):
        impl = _fresh_impl()
        fake_order = MagicMock()
        fake_order.id = "order-bracket"
        fake_order.status = "filled"
        fake_order.filled_avg_price = 149.5
        fake_order.filled_qty = 10
        fake_order.filled_at = None
        impl._c.submit_order_for_account.return_value = fake_order
        impl._c.get_order_for_account_by_id.return_value = fake_order

        order = Order(
            symbol="AAPL", side=OrderSide.BUY, qty=10,
            order_class=OrderClass.BRACKET,
            order_type=OrderType.LIMIT, limit_price=150.0,
            take_profit_price=160.0, stop_loss_price=140.0,
        )
        filled = impl.submit_order(order)
        assert filled.symbol == "AAPL"
        impl._c.submit_order_for_account.assert_called_once()

    def test_submission_failure_raises(self):
        impl = _fresh_impl()
        impl._c.submit_order_for_account.side_effect = RuntimeError("boom")
        order = Order(symbol="AAPL", side=OrderSide.BUY, qty=10)
        with pytest.raises(BrokerError, match="Order submission failed"):
            impl.submit_order(order)


# ── order status / cancel ────────────────────────────────────────────────

class TestOrderLifecycle:
    def test_get_order_status_returns_filled(self):
        impl = _fresh_impl()
        fake = MagicMock()
        fake.id = "o-1"
        fake.symbol = "AAPL"
        fake.side = "buy"
        fake.filled_qty = 10
        fake.filled_avg_price = 150.0
        fake.filled_at = datetime.now(timezone.utc)
        impl._c.get_order_for_account_by_id.return_value = fake

        result = impl.get_order_status("o-1")
        assert result is not None
        assert result.order_id == "o-1"
        assert result.filled_price == 150.0

    def test_get_order_status_not_found(self):
        impl = _fresh_impl()
        impl._c.get_order_for_account_by_id.side_effect = RuntimeError("not found")
        assert impl.get_order_status("bad") is None

    def test_cancel_order_success(self):
        impl = _fresh_impl()
        assert impl.cancel_order("o-1") is True
        impl._c.cancel_order_for_account_by_id.assert_called_once()

    def test_cancel_order_failure(self):
        impl = _fresh_impl()
        impl._c.cancel_order_for_account_by_id.side_effect = RuntimeError("gone")
        assert impl.cancel_order("o-1") is False


# ── positions ────────────────────────────────────────────────────────────

class TestPositions:
    def test_get_position_found(self):
        impl = _fresh_impl()
        pos = MagicMock()
        pos.symbol = "AAPL"
        pos.qty = 10
        pos.avg_entry_price = 145.0
        pos.current_price = 150.0
        pos.unrealized_pl = 50.0
        pos.market_value = 1500.0
        impl._c.get_open_position_for_account.return_value = pos

        result = impl.get_position("AAPL")
        assert result is not None
        assert result.qty == 10
        assert result.current_price == 150.0

    def test_get_position_not_found(self):
        impl = _fresh_impl()
        impl._c.get_open_position_for_account.side_effect = RuntimeError("no pos")
        assert impl.get_position("AAPL") is None


# ── portfolio ────────────────────────────────────────────────────────────

class TestPortfolio:
    def test_portfolio_state(self):
        impl = _fresh_impl()
        acct = MagicMock()
        acct.cash = 90000.0
        acct.equity = 100000.0
        acct.account_number = "123"
        impl._c.get_trade_account_by_id.return_value = acct
        impl._c.get_all_positions_for_account.return_value = []

        state = impl.get_portfolio_state()
        assert state.cash == 90000.0
        assert state.equity == 100000.0
        assert len(state.positions) == 0

    def test_portfolio_failure_raises(self):
        impl = _fresh_impl()
        impl._c.get_trade_account_by_id.side_effect = RuntimeError("down")
        with pytest.raises(BrokerError, match="portfolio"):
            impl.get_portfolio_state()


# ── close position ───────────────────────────────────────────────────────

class TestClosePosition:
    def test_close_success(self):
        impl = _fresh_impl()
        fake = MagicMock()
        fake.id = "close-1"
        fake.qty = 10
        fake.status = "filled"
        fake.filled_avg_price = 155.0
        fake.filled_qty = 10
        fake.filled_at = None
        impl._c.close_position_for_account.return_value = fake
        impl._c.get_order_for_account_by_id.return_value = fake

        result = impl.close_position("AAPL")
        assert result is not None
        assert result.symbol == "AAPL"
        assert result.filled_price == 155.0

    def test_close_failure(self):
        impl = _fresh_impl()
        impl._c.close_position_for_account.side_effect = RuntimeError("no pos")
        assert impl.close_position("AAPL") is None


# ── open orders ──────────────────────────────────────────────────────────

class TestOpenOrders:
    def test_flatten_legs(self):
        impl = _fresh_impl()
        from types import SimpleNamespace
        leg = SimpleNamespace(
            id="leg-1",
            symbol=None,
            side="OrderSide.SELL",
            order_type="OrderType.STOP",
            qty=10,
            limit_price=None,
            stop_price=140.0,
        )
        parent = SimpleNamespace(
            id="parent-1",
            symbol="AAPL",
            side="OrderSide.BUY",
            order_type="OrderType.LIMIT",
            qty=10,
            limit_price=150.0,
            stop_price=None,
        )
        parent.legs = [leg]

        impl._c.get_orders_for_account.return_value = [parent]

        orders = impl.get_open_orders()
        assert len(orders) == 2  # parent + leg

    def test_empty_on_failure(self):
        impl = _fresh_impl()
        impl._c.get_orders_for_account.side_effect = RuntimeError("down")
        assert impl.get_open_orders() == []


# ── fills ────────────────────────────────────────────────────────────────

class TestGetFills:
    def test_typed_trade_activity(self):
        impl = _fresh_impl()
        from alpaca.trading.enums import OrderSide as AlpacaSide, OrderStatus as AlpacaStatus
        from alpaca.trading.models import TradeActivity

        ta = TradeActivity(
            id="fill-1",
            account_id=uuid.UUID(impl._account_id),
            activity_type="FILL",
            transaction_time="2026-05-31T10:00:00Z",
            side=AlpacaSide.BUY,
            symbol="AAPL",
            qty=10,
            price=150.0,
            leaves_qty=0,
            order_id=uuid.uuid4(),
            cum_qty=10,
            type="fill",
            order_status=AlpacaStatus.FILLED,
        )
        impl._c.get_account_activities.return_value = [ta]

        fills = impl.get_fills()
        assert len(fills) == 1
        assert fills[0].fill_id == "fill-1"
        assert fills[0].symbol == "AAPL"
        assert fills[0].qty == 10
        assert fills[0].price == 150.0

    def test_filters_non_trade_activity(self):
        impl = _fresh_impl()
        from alpaca.trading.models import NonTradeActivity

        nta = NonTradeActivity(
            id="nt-1",
            account_id=uuid.UUID(impl._account_id),
            activity_type="DIV",
            transaction_time="2026-05-31T10:00:00Z",
            date="2026-05-31",
            net_amount=50.0,
            description="dividend",
        )
        impl._c.get_account_activities.return_value = [nta]

        fills = impl.get_fills()
        assert fills == []

    def test_best_effort_on_failure(self):
        impl = _fresh_impl()
        impl._c.get_account_activities.side_effect = RuntimeError("down")
        assert impl.get_fills() == []


# ── market data ──────────────────────────────────────────────────────────

class TestLatestPrices:
    def test_happy_path(self):
        impl = _fresh_impl()
        trade = MagicMock()
        trade.price = 150.0
        # StockHistoricalDataClient is imported lazily inside the method;
        # patch the source module (alpaca SDK).
        with patch(
            "alpaca.data.historical.StockHistoricalDataClient"
        ) as mock_s:
            inst = mock_s.return_value
            inst.get_stock_latest_trade.return_value = {"AAPL": trade}

            prices = impl.get_latest_prices(["AAPL"])
            # Check StockHistoricalDataClient was built with basic-auth
            _, kwargs = mock_s.call_args
            assert kwargs.get("use_basic_auth") is True
            assert "data.sandbox" in kwargs.get("url_override", "")
            assert prices == {"AAPL": 150.0}

    def test_lazy_build_once(self):
        impl = _fresh_impl()
        trade = MagicMock()
        trade.price = 150.0
        with patch(
            "alpaca.data.historical.StockHistoricalDataClient"
        ) as mock_s:
            inst = mock_s.return_value
            inst.get_stock_latest_trade.return_value = {"AAPL": trade}
            impl.get_latest_prices(["AAPL"])
            impl.get_latest_prices(["MSFT"])
            assert mock_s.call_count == 1  # built once

    def test_best_effort_on_failure(self):
        impl = _fresh_impl()
        with patch(
            "alpaca.data.historical.StockHistoricalDataClient"
        ) as mock_s:
            inst = mock_s.return_value
            inst.get_stock_latest_trade.side_effect = RuntimeError("down")
            assert impl.get_latest_prices(["AAPL"]) == {}

    def test_empty_symbols(self):
        impl = _fresh_impl()
        assert impl.get_latest_prices([]) == {}
        assert impl.get_latest_prices([""]) == {}


# ── market clock ─────────────────────────────────────────────────────────

class TestMarketClock:
    def test_open(self):
        impl = _fresh_impl()
        clock = MagicMock()
        clock.is_open = True
        impl._c.get_clock.return_value = clock
        assert impl.is_market_open() is True

    def test_closed(self):
        impl = _fresh_impl()
        clock = MagicMock()
        clock.is_open = False
        impl._c.get_clock.return_value = clock
        assert impl.is_market_open() is False

    def test_fail_closed(self):
        impl = _fresh_impl()
        impl._c.get_clock.side_effect = RuntimeError("down")
        assert impl.is_market_open() is False


# ── record_trade_ledger shim ─────────────────────────────────────────────

class TestLedgerShim:
    def test_shim_forwards_get_orders(self):
        impl = _fresh_impl()
        with patch(
            "src.execution.brokers.broker_api_broker.record_trades"
        ) as mock_rt:
            impl.record_trade_ledger("/tmp/ledger.jsonl")
            mock_rt.assert_called_once()
            shim_arg = mock_rt.call_args[0][0]
            assert isinstance(shim_arg, _LedgerClientShim)
            assert shim_arg._account_id == impl._account_id


# ── PBT: pure mapper round-trip (Partial mode) ───────────────────────────

try:
    from hypothesis import assume, given, note, strategies as st

    _HYPOTHESIS_AVAILABLE = True
except ImportError:
    _HYPOTHESIS_AVAILABLE = False


@pytest.mark.skipif(
    not _HYPOTHESIS_AVAILABLE, reason="hypothesis not installed"
)
class TestMappersPBT:
    """Property: _to_fill_event_typed returns FillEvent iff TradeActivity is valid."""

    def test_valid_trade_activity_always_yields_fill(self):
        from alpaca.trading.enums import OrderSide as AlpacaSide, OrderStatus as AlpacaStatus
        from alpaca.trading.models import TradeActivity
        from src.execution.brokers.broker_api_broker import BrokerApiBroker

        ta = TradeActivity(
            id="f-1", account_id=uuid.uuid4(), activity_type="FILL",
            transaction_time="2026-05-31T12:00:00Z",
            side=AlpacaSide.SELL, symbol="MSFT",
            qty=5, price=400.0, leaves_qty=0,
            order_id=uuid.uuid4(), cum_qty=5,
            type="fill", order_status=AlpacaStatus.FILLED,
        )
        result = BrokerApiBroker._to_fill_event_typed(ta)
        assert result is not None
        assert result.fill_id == "f-1"
        # qty is abs()
        assert result.qty == 5
        assert result.side == "sell"

    def test_non_trade_activity_yields_none(self):
        from alpaca.trading.models import NonTradeActivity
        from src.execution.brokers.broker_api_broker import BrokerApiBroker

        nta = NonTradeActivity(
            id="nta-1", account_id=uuid.uuid4(),
            activity_type="DIV", transaction_time="2026-05-31T12:00:00Z",
            date="2026-05-31", net_amount=50.0, description="dividend",
        )
        assert BrokerApiBroker._to_fill_event_typed(nta) is None


# ── _LedgerClientShim isolated tests ─────────────────────────────────────

class TestLedgerShimUnit:
    def test_get_orders_delegates(self):
        c = MagicMock()
        c.get_orders_for_account.return_value = [MagicMock()]
        shim = _LedgerClientShim(c, "acc-1")
        from alpaca.trading.requests import GetOrdersRequest
        req = GetOrdersRequest()
        result = shim.get_orders(filter=req)
        c.get_orders_for_account.assert_called_once_with("acc-1", filter=req)


# ── corrected behaviour (R7 — fixes R3 T3-1 / T3-2) ───────────────────────────
# R3 preserved BrokerApiBroker's divergent side/TIF behaviour behind subclass
# overrides; R7 dropped those overrides so broker_api now inherits the correct
# shared AlpacaShapedBroker behaviour (same as AlpacaBroker). These tests assert
# the corrected values (BUY_TO_COVER→BUY; fail-closed on unsupported TIF).

class TestSideMapping:
    def test_buy_maps_to_buy(self):
        from alpaca.trading.enums import OrderSide as AS
        assert _fresh_impl()._alpaca_side(OrderSide.BUY) == AS.BUY

    def test_sell_maps_to_sell(self):
        from alpaca.trading.enums import OrderSide as AS
        assert _fresh_impl()._alpaca_side(OrderSide.SELL) == AS.SELL

    def test_sell_short_maps_to_sell(self):
        from alpaca.trading.enums import OrderSide as AS
        assert _fresh_impl()._alpaca_side(OrderSide.SELL_SHORT) == AS.SELL

    def test_buy_to_cover_maps_to_buy(self):
        # R7 T3-1 FIX: a short cover is a BUY (was wrongly → SELL under the preserved
        # override). broker_api now inherits the correct shared mapping.
        from alpaca.trading.enums import OrderSide as AS
        assert _fresh_impl()._alpaca_side(OrderSide.BUY_TO_COVER) == AS.BUY

    def test_unknown_side_raises(self):
        # base maps only BUY/BUY_TO_COVER/SELL/SELL_SHORT; anything else is fail-closed.
        # (All OrderSide members are valid, so exercise the guard with a bogus value.)
        with pytest.raises(BrokerError):
            _fresh_impl()._alpaca_side("FOO")


class TestTimeInForce:
    def _o(self, tif, order_class=OrderClass.SIMPLE):
        return Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_type=OrderType.MARKET,
                     time_in_force=tif, order_class=order_class)

    def test_gtc_maps_to_gtc(self):
        from alpaca.trading.enums import TimeInForce
        assert _fresh_impl()._time_in_force(self._o("gtc")) == TimeInForce.GTC

    def test_day_maps_to_day(self):
        from alpaca.trading.enums import TimeInForce
        assert _fresh_impl()._time_in_force(self._o("day")) == TimeInForce.DAY

    def test_ioc_and_fok_supported(self):
        # R7 T3-2 FIX: the shared F9 map supports ioc/fok (no longer downgraded to DAY).
        from alpaca.trading.enums import TimeInForce
        assert _fresh_impl()._time_in_force(self._o("ioc")) == TimeInForce.IOC
        assert _fresh_impl()._time_in_force(self._o("fok")) == TimeInForce.FOK

    def test_unsupported_tif_fails_closed(self):
        # R7 T3-2 FIX: opg/cls/unknown raise instead of silently downgrading to DAY.
        with pytest.raises(BrokerError):
            _fresh_impl()._time_in_force(self._o("opg"))

    def test_bracket_forces_gtc(self):
        from alpaca.trading.enums import TimeInForce
        o = Order(symbol="AAPL", side=OrderSide.BUY, qty=1, order_class=OrderClass.BRACKET,
                  order_type=OrderType.MARKET, take_profit_price=11, stop_loss_price=9,
                  time_in_force="day")
        assert _fresh_impl()._time_in_force(o) == TimeInForce.GTC
