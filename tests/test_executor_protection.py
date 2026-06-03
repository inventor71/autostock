"""protected_symbols keys on a STOP leg, not any open order (F30 MED-3)."""

from __future__ import annotations

from src.agent.executor import DecisionExecutor
from src.core.models import OpenOrder
from src.core.types import OrderSide, OrderType


class _Broker:
    def __init__(self, orders):
        self._orders = orders

    def get_open_orders(self, symbol=None):
        return self._orders


def _ex(orders):
    ex = DecisionExecutor.__new__(DecisionExecutor)  # bypass __init__ (journal/universe)
    ex.broker = _Broker(orders)
    return ex


def test_tp_only_limit_is_not_protected():
    # An emulated OCO whose stop-loss leg was rejected leaves only a TP LIMIT —
    # that must NOT count as protected, so the polled backup re-engages.
    orders = [OpenOrder(order_id="1", symbol="AAA", side=OrderSide.SELL,
                        order_type=OrderType.LIMIT, qty=1, limit_price=100)]
    assert _ex(orders).protected_symbols() == set()


def test_stop_leg_is_protected():
    orders = [
        OpenOrder(order_id="1", symbol="AAA", side=OrderSide.SELL, order_type=OrderType.LIMIT, qty=1),
        OpenOrder(order_id="2", symbol="BBB", side=OrderSide.SELL, order_type=OrderType.STOP, qty=1),
        OpenOrder(order_id="3", symbol="CCC", side=OrderSide.SELL, order_type=OrderType.STOP_LIMIT, qty=1),
    ]
    assert _ex(orders).protected_symbols() == {"BBB", "CCC"}  # stop-type legs only
