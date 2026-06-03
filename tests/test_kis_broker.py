"""Unit tests for KisPaperBroker — mocked REST transport (no network, F30)."""

from __future__ import annotations

import pytest

from src.core.exceptions import BrokerError
from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.brokers.kis_broker import KisBroker, KisPaperBroker, _OcoStore


class FakeKis:
    """Records calls; returns canned KIS responses."""

    def __init__(self, positions=None):
        self.posts = []
        self.gets = []
        self._seq = 0
        self._positions = positions if positions is not None else [
            {"pdno": "005930", "hldg_qty": "10", "pchs_avg_pric": "70000", "prpr": "71000"}
        ]

    def post(self, path, tr, body):
        self.posts.append((path, tr, body))
        if path.endswith("order-cash"):
            self._seq += 1
            return {"rt_cd": "0", "output": {"ODNO": f"O{self._seq}", "KRX_FWDG_ORD_ORGNO": "012"}}
        return {"rt_cd": "0"}

    def get(self, path, tr, params):
        self.gets.append((path, tr, params))
        if path.endswith("inquire-balance"):
            return {"rt_cd": "0", "output1": self._positions,
                    "output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "1710000"}]}
        if path.endswith("inquire-psbl-rvsecncl"):
            return {"rt_cd": "0", "output": []}
        return {"rt_cd": "0", "output": {}}


def make_broker(tmp_path, **kw):
    b = KisPaperBroker("ak", "sk", "12345678-01",
                       oco_journal=tmp_path / "oco.json", fill_poll_timeout=0.0, **kw)
    b._c = FakeKis(kw.pop("positions", None))
    return b


def test_kisbroker_is_abstract_on_arm_stop():
    assert KisBroker.__abstractmethods__ == frozenset({"_arm_stop"})
    assert KisPaperBroker.__abstractmethods__ == frozenset()


def test_market_buy_maps_to_dvsn01_and_floors_qty(tmp_path):
    b = make_broker(tmp_path)
    b.submit_order(Order(symbol="005930", side=OrderSide.BUY, qty=3.7, order_type=OrderType.MARKET))
    path, tr, body = b._c.posts[-1]
    assert path.endswith("order-cash") and tr == "VTTC0012U"
    assert body["ORD_DVSN"] == "01" and body["ORD_QTY"] == "3"


def test_limit_buy_rounds_to_tick(tmp_path):
    b = make_broker(tmp_path)
    b.submit_order(Order(symbol="005930", side=OrderSide.BUY, qty=1,
                         order_type=OrderType.LIMIT, limit_price=70123))
    _, _, body = b._c.posts[-1]
    assert body["ORD_DVSN"] == "00" and body["ORD_UNPR"] == "70100"  # tick 100


def test_sub_one_qty_rejected(tmp_path):
    b = make_broker(tmp_path)
    with pytest.raises(BrokerError):
        b.submit_order(Order(symbol="005930", side=OrderSide.BUY, qty=0.4, order_type=OrderType.MARKET))


def test_trailing_stop_rejected(tmp_path):
    b = make_broker(tmp_path)
    with pytest.raises(BrokerError):
        b.submit_order(Order(symbol="005930", side=OrderSide.SELL, qty=1,
                             order_type=OrderType.TRAILING_STOP, trail_percent=5))


def test_positions_and_portfolio_parsing(tmp_path):
    b = make_broker(tmp_path)
    ps = b.get_all_positions()
    assert len(ps) == 1 and ps[0].symbol == "005930" and ps[0].qty == 10
    pf = b.get_portfolio_state()
    assert pf.cash == 1_000_000 and pf.equity == 1_710_000


def test_oco_paper_arms_tp_limit_and_polled_stop(tmp_path):
    b = make_broker(tmp_path)
    b.submit_order(Order(symbol="005930", side=OrderSide.SELL, qty=5, order_class=OrderClass.OCO,
                         take_profit_price=80000, stop_loss_price=65050))
    assert len(b._oco.groups) == 1
    g = next(iter(b._oco.groups.values()))
    assert g.tp_odno is not None          # TP rests at exchange
    assert g.sl_odno is None              # SL is polled (모의: no exchange stop)
    assert g.stop_price == 65000          # round_to_tick(65050) -> 65000 (tick 100)
    # TP placed as a LIMIT sell
    tp_posts = [p for p in b._c.posts if p[2]["ORD_DVSN"] == "00"]
    assert tp_posts and tp_posts[-1][2]["ORD_UNPR"] == "80000"
    assert (tmp_path / "oco.json").exists()


def test_reconcile_cancels_dangling_tp_when_position_gone(tmp_path):
    b = make_broker(tmp_path)
    b.submit_order(Order(symbol="005930", side=OrderSide.SELL, qty=5, order_class=OrderClass.OCO,
                         take_profit_price=80000, stop_loss_price=65000))
    b._c._positions = []  # position exited (polled SL fired)
    b.reconcile_oco()
    assert not b._oco.groups  # group resolved
    assert any(p[0].endswith("order-rvsecncl") for p in b._c.posts)  # TP cancelled


def test_oco_journal_survives_reload(tmp_path):
    path = tmp_path / "oco.json"
    s1 = _OcoStore(path)
    g = s1.new_group("005930", 7)
    g.tp_odno = "O42"
    g.stop_price = 65000
    s1.save()
    s2 = _OcoStore(path)
    assert g.group_id in s2.groups
    assert s2.groups[g.group_id].tp_odno == "O42" and s2.groups[g.group_id].qty == 7


def test_is_market_open_returns_bool(tmp_path):
    assert isinstance(make_broker(tmp_path).is_market_open(), bool)
