"""Unit A steering-core -- Step 7: CommandHandler verb wiring + build_human_buy."""

from __future__ import annotations

import pandas as pd
import pytest

from src.agent.executor import DecisionExecutor
from src.agent.steering.channel import SteeringChannel
from src.agent.steering.commands import CommandHandler, build_human_buy
from src.agent.steering.records import SteeringCommand, SteeringEvent
from src.agent.steering.state import SteeringState
from src.core.models import Order
from src.core.types import OrderClass, OrderSide
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
        return pd.DataFrame({"open": [500, 500], "high": [500, 500], "low": [500, 500],
                             "close": [500, 500], "volume": [1, 1]}, index=idx)


class _RecordingWorker:
    def __init__(self):
        self.kinds = []

    def trigger(self, run_fn, *, kind="reconcile"):
        self.kinds.append(kind)


def _setup(tmp_path, price=100.0):
    broker = SimulatedBroker(initial_capital=100_000.0)
    broker.set_current_price("AAPL", price)
    rm = RiskManager(use_bracket_orders=True)
    ex = DecisionExecutor(broker, rm, _Provider(price), journal=None, universe=["AAPL", "MSFT"])
    # point the journal/state/channel at the temp dir
    from src.agent.journal import Journal
    ex.journal = Journal(root=tmp_path / "ws")
    ex._state_file = ex.journal.root / ".executor_state.json"
    ex._atr = lambda s: 2.0  # deterministic ATR so a bracket is built
    state = SteeringState(tmp_path / "ws")
    channel = SteeringChannel(tmp_path / "steering", TOKEN)
    worker = _RecordingWorker()
    handler = CommandHandler(channel, state, ex, reconcile_worker=worker,
                             reconcile_run_fn=lambda: None)
    return handler, broker, state, channel, worker


def _cmd(verb, **args):
    return SteeringCommand(verb=verb, args=args, confirmed=True, token=TOKEN)


def _last_event(channel) -> SteeringEvent:
    return SteeringEvent.model_validate_json(channel.events_file.read_text().splitlines()[-1])


# --- build_human_buy (pure) ------------------------------------------------- #
def test_build_human_buy_dollar_floors_to_whole_shares():
    rm = RiskManager(use_bracket_orders=True)
    o = build_human_buy("AAPL", 1000.0, "$", price=100.0, atr=2.0, risk_manager=rm)
    assert o.qty == 10.0 and o.side == OrderSide.BUY
    assert o.order_class == OrderClass.BRACKET and o.stop_loss_price < 100.0 < o.take_profit_price


def test_build_human_buy_shares_and_no_atr_is_simple():
    rm = RiskManager(use_bracket_orders=True)
    o = build_human_buy("AAPL", 7.9, "sh", price=100.0, atr=None, risk_manager=rm)
    assert o.qty == 7.0 and o.order_class == OrderClass.SIMPLE  # floored, no bracket without a stop


def test_build_human_buy_too_small_returns_none():
    rm = RiskManager(use_bracket_orders=True)
    assert build_human_buy("AAPL", 50.0, "$", price=100.0, atr=2.0, risk_manager=rm) is None


# --- handler wiring --------------------------------------------------------- #
def test_buy_executes_locks_and_reconciles(tmp_path):
    h, broker, state, channel, worker = _setup(tmp_path)
    h.handle(_cmd("buy", symbol="AAPL", size=1000.0, unit="$"))
    assert _last_event(channel).payload["outcome"] == "executed"
    assert broker.get_position("AAPL") is not None
    assert state.lock_status("AAPL") == "locked"
    assert worker.kinds == ["human"]  # reconcile triggered


def test_sell_partial_of_position(tmp_path):
    h, broker, state, channel, _ = _setup(tmp_path)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10.0))  # seed a position
    h.handle(_cmd("sell", symbol="AAPL", size=50.0, unit="%"))
    assert _last_event(channel).payload["outcome"] in ("executed", "no_order")
    assert state.lock_status("AAPL") == "locked"


def test_sell_with_no_position_is_no_order(tmp_path):
    h, broker, state, channel, _ = _setup(tmp_path)
    h.handle(_cmd("sell", symbol="MSFT", size=100.0, unit="%"))
    assert _last_event(channel).payload["outcome"] == "no_order"


def test_flatten_closes_position(tmp_path):
    h, broker, state, channel, _ = _setup(tmp_path)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10.0))
    h.handle(_cmd("flatten", symbol="AAPL"))
    assert _last_event(channel).payload["outcome"] == "executed"
    assert broker.get_position("AAPL") is None


def test_lifecycle_pause_resume_halt(tmp_path):
    h, _, state, channel, _ = _setup(tmp_path)
    h.handle(_cmd("pause")); assert state.run_state().paused
    h.handle(_cmd("resume")); assert not state.run_state().paused
    h.handle(_cmd("halt_entries")); assert state.run_state().entries_halted


def test_kill_flattens_and_pauses(tmp_path):
    h, broker, state, channel, _ = _setup(tmp_path)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10.0))
    h.handle(_cmd("kill"))
    assert state.run_state().paused and broker.get_position("AAPL") is None


def test_offhours_trade_is_deferred_and_queued(tmp_path, monkeypatch):
    h, broker, state, channel, _ = _setup(tmp_path)
    monkeypatch.setattr(broker, "is_market_open", lambda: False)
    h.handle(_cmd("buy", symbol="AAPL", size=1000.0, unit="$"))
    assert _last_event(channel).payload["outcome"] == "deferred"
    assert broker.get_position("AAPL") is None
    drained = channel.drain_offhours()
    assert len(drained) == 1 and drained[0].verb == "buy"
    assert drained[0].token == ""  # token not persisted to disk (SECURITY-03)


def test_approve_executes_parked_decision(tmp_path):
    h, broker, state, channel, _ = _setup(tmp_path)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10.0))
    state.lock_symbol("AAPL")
    from src.agent.journal import Decision
    pa = state.add_pending(Decision(symbol="AAPL", action="SELL", source="agent"))
    h.handle(_cmd("approve", id=pa.id))
    assert _last_event(channel).payload["outcome"] in ("executed", "no_order")
    assert state.lock_status("AAPL") is None  # approve unlocks


def test_answer_unknown_id_rejected_then_applied(tmp_path):
    # review #1: an unknown question id is REJECTED (not a false "applied"+orphaned answer)
    h, broker, state, channel, _ = _setup(tmp_path)
    h.handle(_cmd("answer", id="bogus", text="hi"))
    assert _last_event(channel).payload["outcome"] == "rejected"
    assert not (h.journal.root / "agent_answers.jsonl").exists()
    # with a real open question, the answer applies and is persisted
    from src.agent.steering.records import AgentQuestion
    q = AgentQuestion(symbol="AAPL", text="re-enter?")
    h.journal.root.mkdir(parents=True, exist_ok=True)
    (h.journal.root / "agent_questions.jsonl").write_text(q.model_dump_json() + "\n")
    h.handle(_cmd("answer", id=q.id, text="no, stand down"))
    assert _last_event(channel).payload["outcome"] == "applied"
    assert q.id in (h.journal.root / "agent_answers.jsonl").read_text()


def test_stop_above_market_rejected_for_long(tmp_path):
    # review #7: a long's stop at/above market would exit immediately -> reject
    h, broker, state, channel, _ = _setup(tmp_path)  # provider price = 100
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10.0))
    h.handle(_cmd("stop", symbol="AAPL", price=9999.0))
    ev = _last_event(channel)
    assert ev.payload["outcome"] == "no_order"
    assert "would exit immediately" in ev.payload["detail"]
    # a sane stop below market goes through
    h.handle(_cmd("stop", symbol="AAPL", price=90.0))
    assert _last_event(channel).payload["outcome"] in ("executed", "skipped_hold", "no_order")


def test_unknown_verb_errors_without_raising(tmp_path):
    h, _, _, channel, _ = _setup(tmp_path)
    # craft a command whose verb passes schema but has no handler -> error outcome
    cmd = SteeringCommand(verb="pause", confirmed=True, token=TOKEN)
    object.__setattr__(cmd, "verb", "bogus")
    h.handle(cmd)
    assert _last_event(channel).payload["outcome"] == "error"


def test_cancel_queued_offhours_trade_by_full_id(tmp_path):
    h, _, _, channel, _ = _setup(tmp_path)
    queued = _cmd("sell", symbol="AAPL", size=50.0, unit="%")
    channel.queue_offhours(queued)
    assert len(channel.list_offhours()) == 1
    h.handle(_cmd("cancel", target=queued.id))
    assert channel.list_offhours() == []  # removed from the queue
    assert _last_event(channel).payload["outcome"] == "applied"


def test_cancel_queued_offhours_trade_by_short_prefix(tmp_path):
    # The sidebar shows only an 8-char id; pasting that prefix must cancel the trade.
    h, _, _, channel, _ = _setup(tmp_path)
    queued = _cmd("sell", symbol="AAPL", size=50.0, unit="%")
    channel.queue_offhours(queued)
    h.handle(_cmd("cancel", target=queued.id[:8]))
    assert channel.list_offhours() == []
    assert _last_event(channel).payload["outcome"] == "applied"


def test_cancel_ambiguous_prefix_removes_nothing(tmp_path):
    h, _, _, channel, _ = _setup(tmp_path)
    a = SteeringCommand(verb="sell", args={"symbol": "AAPL"}, confirmed=True, token=TOKEN, id="abc1" + "0" * 28)
    b = SteeringCommand(verb="buy", args={"symbol": "MSFT"}, confirmed=True, token=TOKEN, id="abc2" + "0" * 28)
    channel.queue_offhours(a)
    channel.queue_offhours(b)
    h.handle(_cmd("cancel", target="abc"))  # prefix matches both -> refuse
    assert len(channel.list_offhours()) == 2
    ev = _last_event(channel).payload
    assert ev["outcome"] == "no_order" and "ambiguous" in ev["detail"]


def test_cancel_unknown_target_is_no_order(tmp_path):
    h, _, _, channel, _ = _setup(tmp_path)
    h.handle(_cmd("cancel", target="ZZZZ"))  # no queued match, no resting orders
    assert _last_event(channel).payload["outcome"] == "no_order"
