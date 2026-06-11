from datetime import datetime

import pandas as pd

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision, Journal
from src.agent.learning.review import outcome_lines
from src.core.models import OpenOrder, Order
from src.core.types import OrderClass, OrderSide, OrderType
from src.execution.brokers.simulated_broker import SimulatedBroker
from src.risk.manager import RiskManager


def _ohlcv(n: int = 120, start: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series([start + i * 0.5 for i in range(n)], index=idx)
    return pd.DataFrame(
        {"open": close * 0.99, "high": close * 1.01, "low": close * 0.98,
         "close": close, "volume": [1_000_000] * n},
        index=idx,
    )


class _StubProvider:
    """Fixed latest price; synthetic bars; SPY bars with a configurable day-change."""

    def __init__(self, price: float = 100.0, spy_change: float = 0.0):
        self.price = price
        self.spy_change = spy_change
        self._bars = _ohlcv(120)

    def get_latest_price(self, symbol):
        return self.price

    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        if symbol == "SPY":
            idx = pd.date_range("2024-01-01", periods=2, freq="D")
            c0, c1 = 500.0, 500.0 * (1 + self.spy_change)
            return pd.DataFrame(
                {"open": [c0, c1], "high": [c0, c1], "low": [c0, c1],
                 "close": [c0, c1], "volume": [1, 1]},
                index=idx,
            )
        return self._bars.tail(limit)


def _make(tmp_path, price=100.0, spy_change=0.0, max_position_pct=0.5):
    broker = SimulatedBroker(initial_capital=100000.0)
    # The agent executor requires a bracket-mode RiskManager (it builds resting
    # brackets from the agent's levels) — this is now validated at construction
    # rather than silently flipped on the injected object.
    rm = RiskManager(max_position_pct=max_position_pct, use_bracket_orders=True)
    provider = _StubProvider(price=price, spy_change=spy_change)
    journal = Journal(root=tmp_path / "ws")
    ex = DecisionExecutor(broker, rm, provider, journal=journal, universe=["AAPL", "MSFT"])
    return ex, broker, journal


class TestDecisionExecutor:
    def test_buy_places_resting_bracket(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)  # sim needs a price to fill against
        journal.append_decision(Decision(symbol="AAPL", action="BUY", confidence=0.8, stop=95.0, target=120.0))
        outcomes = ex.execute_pending()
        assert outcomes[0].status == "executed"
        pos = broker.get_position("AAPL")
        assert pos is not None and pos.qty > 0
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 95.0 for o in opens)
        assert any(o.limit_price == 120.0 for o in opens)

    def test_idempotent_across_runs(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        assert len(ex.execute_pending()) == 1
        assert ex.execute_pending() == []  # cursor advanced; nothing re-executed

    def test_out_of_universe_rejected(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(symbol="ZZZZ", action="BUY", stop=1.0, target=2.0))
        assert ex.execute_pending()[0].status == "skipped_out_of_universe"

    def test_expired_decision_skipped(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(
            symbol="AAPL", action="BUY", stop=95.0, target=120.0,
            valid_until=datetime(2020, 1, 1),
        ))
        assert ex.execute_pending()[0].status == "skipped_expired"

    def test_hold_skipped(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="HOLD"))
        assert ex.execute_pending()[0].status == "skipped_hold"

    def test_hold_with_stop_protects_held_position(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        broker.set_current_price("AAPL", 300.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))  # seed, unprotected
        journal.append_decision(Decision(symbol="AAPL", action="HOLD", stop=285.0, target=350.0))
        out = ex.execute_pending()
        assert out[0].status == "executed"
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 285.0 for o in opens)   # protective stop now resting
        assert any(o.limit_price == 350.0 for o in opens)  # at the agent's target

    def test_hold_protection_is_idempotent(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        broker.set_current_price("AAPL", 300.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        journal.append_decision(Decision(symbol="AAPL", action="HOLD", stop=285.0, target=350.0))
        assert ex.execute_pending()[0].status == "executed"
        # Same HOLD again -> protection already rests there -> no churn.
        journal.append_decision(Decision(symbol="AAPL", action="HOLD", stop=285.0, target=350.0))
        assert ex.execute_pending()[0].status == "skipped_hold"

    def test_hold_with_stop_but_no_position_skips(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="HOLD", stop=285.0))
        assert ex.execute_pending()[0].status == "skipped_hold"

    def test_batch_dedups_same_symbol_to_latest(self, tmp_path):
        # Two HOLDs for one symbol in a single batch must not place-then-replace
        # (which raced and failed live for TSLA). Only the latest should apply.
        ex, broker, journal = _make(tmp_path)
        broker.set_current_price("AAPL", 300.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        journal.append_decision(Decision(symbol="AAPL", action="HOLD", stop=285.0, target=350.0))
        journal.append_decision(Decision(symbol="AAPL", action="HOLD", stop=285.0, target=360.0))
        outcomes = ex.execute_pending()
        assert len(outcomes) == 1  # collapsed to the latest decision
        opens = broker.get_open_orders("AAPL")
        assert any(o.limit_price == 360.0 for o in opens)       # latest target placed
        assert not any(o.limit_price == 350.0 for o in opens)   # superseded one not placed

    def test_sell_reduces_position(self, tmp_path):
        ex, broker, journal = _make(tmp_path)
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        journal.append_decision(Decision(symbol="AAPL", action="SELL", sell_pct=0.5))
        assert ex.execute_pending()[0].status == "executed"
        assert broker.get_position("AAPL").qty == 5

    def test_circuit_breaker_blocks_buy(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0, spy_change=-0.05)  # market -5%
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        out = ex.execute_pending()
        assert out[0].status == "no_order"  # RiskManager halted new buys
        assert broker.get_position("AAPL") is None

    def test_adjust_stop_tightens_and_keeps_target(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=90.0, target=130.0))
        ex.execute_pending()
        journal.append_decision(Decision(symbol="AAPL", action="ADJUST_STOP", stop=95.0))
        out = ex.execute_pending()
        assert out[-1].status == "executed"
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 95.0 for o in opens)   # tightened 90 -> 95
        assert any(o.limit_price == 130.0 for o in opens)  # target preserved

    def test_defers_execution_when_market_closed(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        broker.is_market_open = lambda: False  # market closed
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        assert ex.execute_pending() == []  # deferred, nothing placed
        assert broker.get_position("AAPL") is None
        # Reopen: the still-pending decision now executes (cursor was untouched).
        broker.is_market_open = lambda: True
        out = ex.execute_pending()
        assert out and out[0].status == "executed"
        assert broker.get_position("AAPL") is not None

    def test_adjust_stop_ratchet_rejects_loosening(self, tmp_path):
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=90.0, target=130.0))
        ex.execute_pending()
        journal.append_decision(Decision(symbol="AAPL", action="ADJUST_STOP", stop=85.0))  # looser
        ex.execute_pending()
        opens = broker.get_open_orders("AAPL")
        assert any(o.stop_price == 90.0 for o in opens)  # stays at 90 (tighten-only)

    # ------------------------------------------------------------------ #
    # F52: selective cursor advancement + persistent outcome logging
    # ------------------------------------------------------------------ #
    def test_cursor_stops_at_error_and_retries(self, tmp_path):
        """Error outcome -> cursor stays before it; retry succeeds next cycle."""
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        broker.set_current_price("MSFT", 100.0)

        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))  # index 0
        journal.append_decision(Decision(symbol="MSFT", action="BUY", stop=95.0, target=120.0))  # index 1

        # Break MSFT's price fetch -> error
        _orig = ex.data_provider.get_latest_price
        def _fail_msft(symbol):
            if symbol == "MSFT":
                raise RuntimeError("price unavailable")
            return _orig(symbol)
        ex.data_provider.get_latest_price = _fail_msft

        outcomes = ex.execute_pending()
        assert any(o.decision.symbol == "AAPL" and o.status == "executed" for o in outcomes)
        assert any(o.decision.symbol == "MSFT" and o.status == "error" for o in outcomes)

        cursor, terminal = ex._load_cursor()
        assert cursor == 1, f"expected cursor=1 (stops at MSFT), got {cursor}"
        assert 0 in terminal
        assert 1 not in terminal

        # Fix MSFT price -> should execute on next cycle
        ex.data_provider.get_latest_price = lambda s: 100.0
        outcomes2 = ex.execute_pending()
        assert any(o.decision.symbol == "MSFT" and o.status == "executed" for o in outcomes2)
        cursor2, terminal2 = ex._load_cursor()
        assert cursor2 == 2
        assert 1 in terminal2

    def test_cursor_stops_at_no_order(self, tmp_path):
        """RiskManager returns None -> cursor stays; retries when condition clears."""
        ex, broker, journal = _make(tmp_path, price=100.0, spy_change=-0.05)  # breaker tripped
        broker.set_current_price("AAPL", 100.0)

        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        outcomes = ex.execute_pending()
        assert outcomes[0].status == "no_order"

        cursor, terminal = ex._load_cursor()
        assert cursor == 0, "cursor must not advance past retryable no_order"
        assert 0 not in terminal

        # Clear breaker AND fix the SPY feed so _update_market_halt() doesn't
        # re-trip it on the next execute_pending call.
        ex.risk_manager.update_market_halt(0.01)
        ex.data_provider.spy_change = 0.01
        outcomes2 = ex.execute_pending()
        assert any(o.status == "executed" for o in outcomes2)
        assert broker.get_position("AAPL") is not None

    def test_cursor_advances_past_legitimate_skips(self, tmp_path):
        """skipped_hold, skipped_out_of_universe, skipped_expired are terminal."""
        ex, broker, journal = _make(tmp_path)
        journal.append_decision(Decision(symbol="AAPL", action="HOLD"))                        # 0: skipped_hold
        journal.append_decision(Decision(symbol="ZZZZ", action="BUY", stop=1.0, target=2.0))   # 1: out-of-universe
        journal.append_decision(Decision(                                                       # 2: expired
            symbol="MSFT", action="BUY", stop=95.0, target=120.0,
            valid_until=datetime(2020, 1, 1),
        ))

        outcomes = ex.execute_pending()
        assert all(o.status.startswith("skipped_") for o in outcomes)

        cursor, terminal = ex._load_cursor()
        assert cursor == 3, f"expected cursor=3, got {cursor}"
        assert terminal == {0, 1, 2}

    def test_outcome_logging_persists_all_statuses(self, tmp_path):
        """execution_outcomes.jsonl records ALL outcomes with correct fields."""
        import json
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)
        broker.set_current_price("MSFT", 100.0)

        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        journal.append_decision(Decision(symbol="MSFT", action="HOLD"))

        ex.execute_pending()

        log_file = journal.root / "execution_outcomes.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        entries = [json.loads(l) for l in lines]
        assert {e["symbol"] for e in entries} == {"AAPL", "MSFT"}
        assert {e["status"] for e in entries} == {"executed", "skipped_hold"}
        for e in entries:
            for key in ("decision_index", "symbol", "action", "status", "detail", "order_id", "ts"):
                assert key in e, f"missing key {key} in outcome entry"

    def test_mixed_batch_partial_advance(self, tmp_path):
        """AAPL executed + MSFT error -> cursor stops at MSFT; GOOGL not yet attempted."""
        # Use a broader universe so all symbols are in-scope.
        ex, broker, journal = _make(tmp_path, price=100.0)
        ex.universe = {"AAPL", "MSFT", "GOOGL"}
        broker.set_current_price("AAPL", 100.0)
        broker.set_current_price("MSFT", 100.0)
        broker.set_current_price("GOOGL", 100.0)

        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))   # 0
        journal.append_decision(Decision(symbol="MSFT", action="BUY", stop=95.0, target=120.0))   # 1
        journal.append_decision(Decision(symbol="GOOGL", action="BUY", stop=95.0, target=120.0))  # 2

        # Break MSFT price fetch
        _orig = ex.data_provider.get_latest_price
        def _fail_msft(symbol):
            if symbol == "MSFT":
                raise RuntimeError("no data")
            return _orig(symbol)
        ex.data_provider.get_latest_price = _fail_msft

        outcomes = ex.execute_pending()
        assert any(o.decision.symbol == "AAPL" and o.status == "executed" for o in outcomes)
        assert any(o.decision.symbol == "MSFT" and o.status == "error" for o in outcomes)

        cursor, terminal = ex._load_cursor()
        assert cursor == 1, f"cursor should stop at MSFT (index 1), got {cursor}"
        assert 0 in terminal       # AAPL resolved
        assert 1 not in terminal   # MSFT not resolved
        assert 2 in terminal       # GOOGL executed (after MSFT in batch; terminal but cursor stops at MSFT gap)

        # Second cycle: fix MSFT -> MSFT executes
        ex.data_provider.get_latest_price = lambda s: 100.0
        outcomes2 = ex.execute_pending()
        assert any(o.decision.symbol == "MSFT" and o.status == "executed" for o in outcomes2)
        cursor2, terminal2 = ex._load_cursor()
        assert cursor2 == 3
        assert terminal2 == {0, 1, 2}

    def test_backward_compat_old_cursor_format(self, tmp_path):
        """Old state file without terminal_indices -> cursor loads, first run
        re-processes from cursor (safe because old code already advanced past
        everything unconditionally)."""
        import json
        ex, broker, journal = _make(tmp_path, price=100.0)
        broker.set_current_price("AAPL", 100.0)

        # Write old-format state
        ex._state_file.parent.mkdir(parents=True, exist_ok=True)
        ex._state_file.write_text(json.dumps({"cursor": 0, "updated_at": "2026-01-01T00:00:00"}))

        journal.append_decision(Decision(symbol="AAPL", action="BUY", stop=95.0, target=120.0))
        outcomes = ex.execute_pending()
        assert outcomes[0].status == "executed"

        cursor, terminal = ex._load_cursor()
        assert cursor == 1
        assert terminal == {0}
    def test_skips_position_with_resting_protection(self, tmp_path):
        broker = SimulatedBroker(initial_capital=100000.0)
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(
            symbol="AAPL", side=OrderSide.BUY, qty=10,
            order_class=OrderClass.BRACKET, take_profit_price=140.0, stop_loss_price=80.0,
        ))
        ex = DecisionExecutor(broker, RiskManager(use_bracket_orders=True), _StubProvider(price=92.0),
                              journal=Journal(root=tmp_path / "ws"), universe=["AAPL"])
        # Price -8% (beyond the 5% polled threshold), but a resting stop covers it.
        assert ex.run_risk_exits() == []
        assert broker.get_position("AAPL") is not None

    def test_fires_for_unprotected_position(self, tmp_path):
        broker = SimulatedBroker(initial_capital=100000.0)
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))  # no protection
        ex = DecisionExecutor(broker, RiskManager(use_bracket_orders=True), _StubProvider(price=92.0),
                              journal=Journal(root=tmp_path / "ws"), universe=["AAPL"])
        filled = ex.run_risk_exits()  # -8% with no resting stop -> backup fires
        assert len(filled) == 1
        assert broker.get_position("AAPL") is None


class TestOutcomeReview:
    def test_held_position_line(self):
        broker = SimulatedBroker()
        broker.set_current_price("AAPL", 300.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        lines = outcome_lines(
            [Decision(symbol="AAPL", action="BUY", limit=295.0, stop=280.0, target=335.0)],
            broker, _StubProvider(price=310.0),
        )
        assert "AAPL BUY" in lines[0]
        assert "held 10@300.00" in lines[0]
        assert "now 310.00" in lines[0]
        assert "open" in lines[0]

    def test_entry_pending_when_not_filled(self):
        lines = outcome_lines(
            [Decision(symbol="AAPL", action="BUY", limit=295.0, stop=280.0)],
            SimulatedBroker(), _StubProvider(price=310.0),
        )
        assert "entry pending" in lines[0]

    def test_below_stop_status(self):
        broker = SimulatedBroker()
        broker.set_current_price("AAPL", 270.0)
        broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=10))
        lines = outcome_lines(
            [Decision(symbol="AAPL", action="BUY", stop=280.0, target=335.0)],
            broker, _StubProvider(price=270.0),
        )
        assert "at/below stop" in lines[0]


class TestSimulatedOpenOrders:
    def test_maps_resting_legs(self, tmp_path):
        broker = SimulatedBroker()
        broker.set_current_price("AAPL", 100.0)
        broker.submit_order(Order(
            symbol="AAPL", side=OrderSide.BUY, qty=10,
            order_class=OrderClass.BRACKET, take_profit_price=120.0, stop_loss_price=90.0,
        ))
        opens = broker.get_open_orders("AAPL")
        assert {o.order_type for o in opens} == {OrderType.LIMIT, OrderType.STOP}
        assert all(o.side == OrderSide.SELL for o in opens)


class TestCancelAndWait:
    def test_polls_until_orders_clear(self, tmp_path):
        # _cancel_and_wait must cancel, then poll until the broker reports no
        # open orders (Alpaca cancels async -> qty stays held until it settles),
        # so a replacement isn't submitted while the qty is still reserved.
        ex, _, _ = _make(tmp_path)
        leg = OpenOrder(
            order_id="x", symbol="AAPL", side=OrderSide.SELL,
            order_type=OrderType.STOP, qty=10, stop_price=90.0,
        )
        cancelled, polls = [], {"n": 0}

        class _AsyncCancelBroker:
            def cancel_order(self, order_id):
                cancelled.append(order_id)
                return True

            def get_open_orders(self, symbol=None):
                polls["n"] += 1
                return [leg] if polls["n"] <= 2 else []  # clears on the 3rd poll

        ex.broker = _AsyncCancelBroker()
        ex._cancel_and_wait("AAPL", [leg], timeout=2.0, interval=0.01)
        assert cancelled == ["x"]  # the order was cancelled
        assert polls["n"] >= 3     # waited (polled) until open orders cleared
