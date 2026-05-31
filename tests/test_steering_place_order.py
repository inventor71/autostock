"""F9 U-DAEMON — structured order verbs (place_order/cancel_order/cancel_all/
replace_order/close_position/close_all) + the now-gated /buy shorthand.

Verifies the daemon routes structured orders through RiskManager.receive_human_order
(FR-5), enforces FR-7 (notional×non-market), and emits structured rejects (FR-6).
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.agent.executor import DecisionExecutor
from src.agent.journal import Journal
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler
from src.agent.steering.records import SteeringCommand, SteeringEvent
from src.agent.steering.state import SteeringState
from src.core.types import OrderClass
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.manager import RiskManager

TOKEN = "tok"


class _Provider:
    def __init__(self, price=100.0):
        self.price = price

    def get_latest_price(self, symbol):
        return self.price

    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        idx = pd.date_range("2024-01-01", periods=2, freq="D")
        return pd.DataFrame({"open": [100, 100], "high": [100, 100], "low": [100, 100],
                             "close": [100, 100], "volume": [1, 1]}, index=idx)


class _Worker:
    def __init__(self):
        self.kinds = []

    def trigger(self, run_fn, *, kind="reconcile"):
        self.kinds.append(kind)


def _setup(tmp_path, price=100.0, capital=100_000.0):
    broker = SimulatedBroker(initial_capital=capital)
    broker.set_current_price("AAPL", price)
    broker.set_current_price("MSFT", price)
    rm = RiskManager(use_bracket_orders=True)
    ex = DecisionExecutor(broker, rm, _Provider(price), journal=None, universe=["AAPL", "MSFT"])
    ex.journal = Journal(root=tmp_path / "ws")
    ex._state_file = ex.journal.root / ".executor_state.json"
    ex._atr = lambda s: 2.0
    state = SteeringState(tmp_path / "ws")
    channel = SteeringChannel(tmp_path / "steering", TOKEN)
    handler = CommandHandler(channel, state, ex, reconcile_worker=_Worker(),
                             reconcile_run_fn=lambda: None)
    return handler, broker, state, channel, rm


def _cmd(verb, **args):
    return SteeringCommand(verb=verb, args=args, confirmed=True, token=TOKEN)


def _last(channel) -> SteeringEvent:
    return SteeringEvent.model_validate_json(channel.events_file.read_text().splitlines()[-1])


def _outcome(channel) -> str:
    return _last(channel).payload.get("outcome", "")


# --- place_order ----------------------------------------------------------- #
def test_place_order_market_buy_gated_and_bracketed(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", qty=10))
    assert _outcome(channel) == "executed"
    pos = broker.get_position("AAPL")
    assert pos is not None and pos.qty == 10
    # auto-protect attached a resting bracket (atr=2.0 -> stop resolvable)
    assert broker.get_open_orders("AAPL")  # resting protective legs


def test_place_order_notional_resolves_shares(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", notional=550))  # 550/100 = 5
    assert _outcome(channel) == "executed"
    assert broker.get_position("AAPL").qty == 5


def test_place_order_notional_non_market_rejected_defense_in_depth(tmp_path):
    # F21: notional market+day-only check lives at L1 (zod .refine()); L3 keeps
    # defense-in-depth for L1-bypass scenarios. A direct daemon write with
    # notional+limit should still be rejected.
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", notional=550,
                  order_type="limit", limit_price=99))
    assert _outcome(channel) == "rejected"
    assert "notional" in _last(channel).payload.get("detail", "")


def test_place_order_extra_key_rejected(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", qty=1, bogus=True))
    assert _outcome(channel) == "rejected"


def test_place_order_unsupported_tif_rejected(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", qty=1, time_in_force="opg"))
    assert _outcome(channel) == "rejected"
    assert "UNSUPPORTED_TIF" in _last(channel).payload.get("detail", "")


def test_place_order_clamps_on_tight_budget(tmp_path):
    # small account -> position sizer caps shares below the requested 10_000
    h, broker, state, channel, rm = _setup(tmp_path, capital=10_000.0)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", qty=10_000))
    assert _outcome(channel) == "executed"
    assert broker.get_position("AAPL").qty < 10_000


# --- gated /buy shorthand (critic fix) ------------------------------------- #
def test_buy_shorthand_now_blocked_by_breaker(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    rm.update_market_halt(-0.05)  # trip circuit breaker
    h.handle(_cmd("buy", symbol="AAPL", size=1, unit="sh"))
    assert _outcome(channel) == "rejected"
    assert "BREAKER_HALTED" in _last(channel).payload.get("detail", "")
    assert broker.get_position("AAPL") is None  # nothing submitted


def test_buy_shorthand_force_overrides_breaker(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    rm.update_market_halt(-0.05)
    h.handle(_cmd("buy", symbol="AAPL", size=1, unit="sh", force=True))
    assert _outcome(channel) == "executed"
    assert broker.get_position("AAPL") is not None


# --- management verbs ------------------------------------------------------ #
def test_cancel_all_reports_count(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("cancel_all"))
    assert _outcome(channel) == "applied"


def test_close_position(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("place_order", symbol="AAPL", side="buy", qty=10))
    h.handle(_cmd("close_position", symbol="AAPL"))
    assert _outcome(channel) == "executed"
    assert broker.get_position("AAPL") is None


def test_close_position_no_position(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("close_position", symbol="MSFT"))
    assert _outcome(channel) == "no_order"


def test_replace_order_unsupported_on_simulated(tmp_path):
    # SimulatedBroker inherits BaseBroker.replace_order -> None (unsupported);
    # the handler surfaces the bracket/cancel-and-replace guidance.
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("replace_order", order_id="sim_resting_1", qty=5))
    assert _outcome(channel) == "no_order"
    assert "cancel and re-place" in _last(channel).payload.get("detail", "")


def test_cancel_order_missing_id(tmp_path):
    h, broker, state, channel, rm = _setup(tmp_path)
    h.handle(_cmd("cancel_order"))
    assert _outcome(channel) == "no_order"
