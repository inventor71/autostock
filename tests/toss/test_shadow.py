import copy
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from src.core.exceptions import BrokerError
from src.core.models import Order
from src.core.types import OrderClass, OrderSide, OrderType
from src.evals.toss_shadow import ShadowExecutor, claim_turn, do_turn, run
from src.execution.brokers.toss.shadow import TossShadowBroker, parse_book


@pytest.fixture
def shadow(client_factory, tmp_path, monkeypatch):
    now = [datetime(2026, 11, 23, 15, tzinfo=UTC)]
    feed = {"rate": "0.001", "end": None, "fee_error": False, "open": True,
            "timestamp": None, "bid": 99, "ask": 101, "volume": 20, "invalid": False}

    def route(request):
        assert request.method == "GET"  # This fixture's account API cannot accept orders.
        path = request.url.path
        if path == "/api/v1/holdings":
            return {"items": [{"symbol": "AAPL", "currency": "USD", "marketCountry": "US",
                               "quantity": "2", "averagePurchasePrice": "80", "lastPrice": "100",
                               "marketValue": {"amount": "200"}, "profitLoss": {"amount": "40"}}]}
        if path == "/api/v1/buying-power":
            return {"currency": "USD", "cashBuyingPower": "1000"}
        if path == "/api/v1/commissions":
            if feed["fee_error"]:
                return httpx.Response(403)
            return [{"marketCountry": "US", "commissionRate": feed["rate"], "endDate": feed["end"]}]
        if path == "/api/v1/market-calendar/US":
            session = {"startTime": now[0].replace(hour=14, minute=30, second=0, microsecond=0).isoformat(),
                       "endTime": now[0].replace(hour=21, minute=0, second=0, microsecond=0).isoformat()} if feed["open"] else None
            return {"today": {"regularMarket": session}}
        if path == "/api/v1/orderbook":
            return {"currency": "USD", "timestamp": None if feed["invalid"] else
                    (feed["timestamp"] or now[0]).isoformat(),
                    "bids": [{"price": str(feed["bid"]), "volume": str(feed["volume"])}],
                    "asks": [{"price": str(feed["ask"]), "volume": str(feed["volume"])}]}
        raise AssertionError(path)

    client, calls = client_factory(route)
    broker = TossShadowBroker(client, tmp_path / "shadow", clock=lambda: now[0])
    broker.initialize(days=7, symbols=["AAPL", "MSFT"], slippage_bps=0)
    with broker.transaction() as state:
        state["runner"] = {"max_turns_per_day": 2, "interval_minutes": 60}
    monkeypatch.setattr("src.execution.brokers.toss.shadow.time.sleep", lambda _: None)

    def advance(seconds=2):
        now[0] += timedelta(seconds=seconds)
        return broker.poll()

    return SimpleNamespace(broker=broker, client=client, calls=calls, now=now, feed=feed, advance=advance)


def test_seed_is_once_and_hold_book_is_identical_without_trades(shadow):
    b = shadow.broker
    assert b.read()["initial"]["equity"] == 1200
    assert b.get_position("AAPL").avg_entry_price == 80  # historical basis retained, not counted as new P&L
    with pytest.raises(BrokerError, match="already exists"):
        b.initialize()
    shadow.feed.update(bid=103, ask=105)
    report = shadow.advance()
    assert report["equity_usd"] == report["hold_equity_usd"] == 1208
    assert report["excess_return_pct_points"] == 0
    assert report["fees_usd"] == 0
    assert len([r for r in shadow.calls if r.url.path == "/api/v1/holdings"]) == 1


def test_partial_fills_use_ask_and_do_not_reconsume_same_liquidity_after_restart(shadow):
    b = shadow.broker
    submitted = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=3))
    assert submitted.qty == 0
    assert b.get_portfolio_state().cash < 1000  # pending reservation
    shadow.feed["timestamp"] = shadow.now[0]
    shadow.advance()  # source timestamp predates activation
    assert b.get_order_status(submitted.order_id).qty == 0
    shadow.feed["timestamp"] = shadow.now[0]
    b.poll()
    assert b.get_order_status(submitted.order_id).qty == 2
    assert b.read()["cash"] == pytest.approx(797.79)
    restarted = TossShadowBroker(shadow.client, b.root, clock=lambda: shadow.now[0])
    restarted.poll()
    assert restarted.get_order_status(submitted.order_id).qty == 2
    shadow.feed["timestamp"] = None
    shadow.advance()
    filled = restarted.get_order_status(submitted.order_id)
    assert filled.qty == 3 and filled.filled_price == 101
    assert filled.commission == pytest.approx(0.31)
    assert restarted.get_position("AAPL").qty == 5
    assert restarted.read()["cash"] == pytest.approx(696.69)


def test_sell_uses_bid_charges_tax_once_and_reconciles_baseline(shadow):
    b = shadow.broker
    b.submit_order(Order(symbol="AAPL", side=OrderSide.SELL, qty=2))
    report = shadow.advance()
    assert b.get_position("AAPL") is None
    assert report["equity_usd"] == pytest.approx(1197.79)
    assert report["hold_equity_usd"] == 1200
    assert report["fees_usd"] == pytest.approx(0.21)
    assert report["execution_shortfall_usd"] == pytest.approx(2)
    assert report["equity_usd"] - report["hold_equity_usd"] == pytest.approx(-2.21)
    assert b.read()["fills"][0]["regulatory"] == 0.01
    assert len(b.get_fills()) == 1


def test_limit_does_not_fill_on_last_trade_or_touch_only(shadow):
    b = shadow.broker
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1,
                                  order_type=OrderType.LIMIT, limit_price=100))
    shadow.advance()
    assert b.get_order_status(placed.order_id).qty == 0  # mid=100, ask=101
    shadow.feed.update(ask=100)
    shadow.advance()
    assert b.get_order_status(placed.order_id).filled_price == 100


def test_stale_missing_and_crossed_books_never_fill(shadow):
    b = shadow.broker
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1))
    shadow.feed["timestamp"] = shadow.now[0] - timedelta(seconds=30)
    assert shadow.advance()["health"]["status"] == "blocked"
    shadow.feed["invalid"] = True
    assert shadow.advance()["health"]["book_errors"]
    shadow.feed.update(invalid=False, timestamp=None, bid=102, ask=101)
    shadow.advance()
    assert b.get_order_status(placed.order_id).qty == 0


def test_virtual_stop_waits_then_fills_at_gap_price_and_cancels_oco_peer(shadow):
    b = shadow.broker
    b.submit_order(Order(symbol="AAPL", side=OrderSide.SELL, qty=2,
                         order_class=OrderClass.OCO, stop_loss_price=95, take_profit_price=105))
    shadow.feed.update(bid=90, ask=91)
    shadow.advance()
    assert not b.get_fills()  # trigger, not an instantaneous ideal stop-price fill
    shadow.feed.update(bid=85, ask=86)
    shadow.advance()
    assert b.get_fills()[0].price == 85
    assert not b.get_open_orders()
    assert b.get_position("AAPL") is None


def test_cancel_partial_entry_preserves_protection_and_oco_never_oversells(shadow):
    b = shadow.broker
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=3,
                                  order_class=OrderClass.BRACKET, stop_loss_price=95, take_profit_price=105))
    shadow.advance()
    assert b.get_order_status(placed.order_id).qty == 2
    assert b.cancel_order(placed.order_id)
    assert len(b.get_open_orders()) == 2
    shadow.feed.update(bid=110, ask=111, volume=100)
    shadow.advance()
    assert b.get_position("AAPL").qty == 2  # just the mirrored original shares remain
    shadow.feed.update(bid=80, ask=81)
    shadow.advance()
    shadow.advance()
    assert b.get_position("AAPL").qty == 2  # canceled peer cannot consume the original holding


def test_fee_change_between_partial_fills_does_not_reprice_previous_fills(shadow):
    b = shadow.broker
    shadow.now[0] = datetime(2026, 11, 23, 14, 59, 55, tzinfo=UTC)
    shadow.feed["end"] = "2026-11-23"
    b.costs.schedule.get(force=True)
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=4))
    shadow.advance()
    assert b.get_order_status(placed.order_id).commission == 0.21
    shadow.feed["rate"] = "0.002"
    shadow.feed["end"] = None
    shadow.advance(6)
    assert b.get_order_status(placed.order_id).qty == 4
    assert b.get_order_status(placed.order_id).commission == 0.61
    assert b.read()["cash"] == pytest.approx(595.39)
    assert [f["commission"] for f in b.read()["fills"]] == pytest.approx([0.21, 0.40])


def test_expired_fee_failure_pauses_fills_then_recovers(shadow):
    b = shadow.broker
    shadow.now[0] = datetime(2026, 11, 23, 14, 59, 55, tzinfo=UTC)
    shadow.feed["end"] = "2026-11-23"
    b.costs.schedule.get(force=True)
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1))
    shadow.feed["fee_error"] = True
    report = shadow.advance(6)
    assert report["health"]["cost_error"]
    assert b.get_order_status(placed.order_id).qty == 0
    shadow.feed.update(fee_error=False, end=None, rate="0.002")
    shadow.advance()
    assert b.get_order_status(placed.order_id).commission == 0.21


def test_no_borrowing_and_pending_entries_reserve_cash(shadow):
    b = shadow.broker
    b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=8))
    with pytest.raises(BrokerError, match="unreserved"):
        b.submit_order(Order(symbol="MSFT", side=OrderSide.BUY, qty=3))
    with pytest.raises(BrokerError):
        b.submit_order(Order(symbol="AAPL", side=OrderSide.SELL, qty=3))
    with pytest.raises(BrokerError):
        b.submit_order(Order(symbol="AAPL", side=OrderSide.SELL_SHORT, qty=1))


def test_orders_expire_at_session_end_and_run_deadline_survives_restart(shadow):
    b = shadow.broker
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1,
                                  order_type=OrderType.LIMIT, limit_price=50))
    shadow.advance(6 * 3600 + 1)
    assert not b.get_open_orders()
    assert b.get_order_status(placed.order_id).qty == 0
    shadow.now[0] += timedelta(days=7)
    restarted = TossShadowBroker(shadow.client, b.root, clock=lambda: shadow.now[0])
    with pytest.raises(BrokerError):
        restarted.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1))


def test_turn_attempt_budget_is_durable_and_failed_calls_are_counted(shadow):
    b = shadow.broker
    turn = claim_turn(b)
    assert turn["kind"] == "research"
    assert claim_turn(b) is None
    loop = SimpleNamespace(run_morning_research=lambda: (_ for _ in ()).throw(TimeoutError()))
    do_turn(b, loop, None, turn, threading.Event())
    assert b.read()["turns"][0]["status"] == "error"
    shadow.now[0] += timedelta(hours=1)
    restarted = TossShadowBroker(shadow.client, b.root, clock=lambda: shadow.now[0])
    assert claim_turn(restarted)["kind"] == "intraday"
    shadow.now[0] += timedelta(hours=1)
    assert claim_turn(b) is None


def test_observe_once_never_builds_or_calls_agent(shadow, monkeypatch):
    monkeypatch.setattr("src.evals.toss_shadow.build_agent", lambda *_: pytest.fail("must not call model"))
    report = run(shadow.broker, None, once=True)
    assert report["agent_turn_count"] == 0
    assert all(r.method == "GET" for r in shadow.calls if r.url.path.startswith("/api/"))


def test_account_is_private_and_ledger_missing_or_corrupt_fails_closed(shadow):
    b = shadow.broker
    assert b.path.stat().st_mode & 0o777 == 0o600
    assert b.root.stat().st_mode & 0o777 == 0o700
    state = copy.deepcopy(b.read())
    state["source_identity"] = "different-account"
    from src.execution.brokers.toss import storage
    storage.write_json(b.path, state)
    with pytest.raises(BrokerError, match="different"):
        b.get_portfolio_state()
    b.path.write_text("{")
    with pytest.raises(BrokerError, match="invalid"):
        b.get_portfolio_state()
    b.path.unlink()
    with pytest.raises(BrokerError, match="Initialize"):
        b.get_portfolio_state()


@pytest.mark.parametrize("row", [{}, {"timestamp": "2026-11-23T15:00:00", "currency": "USD"}])
def test_incomplete_book_is_not_execution_evidence(row):
    with pytest.raises(BrokerError):
        parse_book(row, datetime(2026, 11, 23, 15, tzinfo=UTC))


def test_agent_decision_risk_gate_fill_and_crash_recovery_share_one_ledger(shadow, tmp_path):
    from src.agent.journal import Decision, Journal
    from src.risk.manager import RiskManager

    b = shadow.broker
    journal = Journal(tmp_path / "journal")
    journal.init()
    provider = SimpleNamespace(get_latest_price=lambda _: 100)
    risk = RiskManager(use_bracket_orders=True, max_position_pct=0.5)
    executor = ShadowExecutor(b, risk, provider, journal, universe=["MSFT", "AAPL"])
    decision = Decision(ts=shadow.now[0], symbol="MSFT", action="BUY", confidence=1,
                        stop=95, target=115, ref_price=100)
    first = executor.execute_decision(decision, decision_index=0)
    assert first.status == "executed"
    order_count = len(b.read()["orders"])
    # Crash after virtual order commit, before executor cursor persistence.
    restarted = ShadowExecutor(b, risk, provider, journal, universe=["MSFT", "AAPL"])
    recovered = restarted.execute_decision(decision, decision_index=0)
    assert recovered.order_id == first.order_id
    assert len(b.read()["orders"]) == order_count
    shadow.advance()
    assert b.get_position("MSFT").qty == 2
    assert b.get_order_status(first.order_id).commission > 0
    assert b.report()["net_return_pct"] < b.report()["hold_return_pct"]  # spread + fees, no invented edge
    assert len(b.get_open_orders("MSFT")) == 3  # remainder and protection for partial entry


def test_agent_turn_does_not_stop_quote_polling(shadow, monkeypatch):
    second_poll = threading.Event()
    executed = threading.Event()
    count = [0]
    original_poll = shadow.broker.poll

    def poll():
        result = original_poll()
        count[0] += 1
        if count[0] >= 2:
            second_poll.set()
        return result

    def research():
        assert second_poll.wait(4), "quote observation stopped during model reasoning"
        return SimpleNamespace(raw={})

    monkeypatch.setattr(shadow.broker, "poll", poll)
    monkeypatch.setattr("src.evals.toss_shadow.build_agent", lambda *_: (
        SimpleNamespace(run_morning_research=research), SimpleNamespace(execute_pending=executed.set)))
    report = run(shadow.broker, None, agent=True, seconds=1.1, poll_seconds=1)
    assert second_poll.is_set() and executed.is_set()
    assert report["agent_turn_count"] == 1


def test_stop_during_reasoning_never_executes_completed_decisions(shadow):
    turn = claim_turn(shadow.broker)
    stop = threading.Event()
    stop.set()
    do_turn(shadow.broker, SimpleNamespace(run_morning_research=lambda: SimpleNamespace(raw={})),
            SimpleNamespace(execute_pending=lambda: pytest.fail("stopped runner executed decisions")), turn, stop)
    assert shadow.broker.read()["turns"][0]["status"] == "stopped"


def test_duplicate_runner_is_rejected_immediately(shadow):
    from src.execution.brokers.toss import storage
    with storage.locked(shadow.broker.root / "runner.lock"), pytest.raises(BrokerError, match="active runner"):
        run(shadow.broker, None, once=True)


def test_config_factory_and_agent_cli_resolve_only_the_virtual_account(shadow, monkeypatch):
    import os

    from config.config import get_settings
    from src.agent.tools.__main__ import _broker, _universe
    from src.evals.toss_shadow import configure_environment

    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr("src.execution.brokers.factory.create_toss_client", lambda *a, **kw: shadow.client)
    try:
        settings = configure_environment(shadow.broker.root)
        assert settings.broker.provider == "toss_shadow" and settings.broker.paper
        assert settings.toss.read_only and settings.data.provider == "toss"
        assert _universe() == ["AAPL", "MSFT"]
        b = _broker()
        assert b.get_portfolio_state().equity == 1200
        assert not any(r.url.path.startswith("/api/v1/orders") for r in shadow.calls)
        from main import run_agent
        with pytest.raises(ValueError, match="isolated workspace"):
            run_agent(settings)
    finally:
        get_settings.cache_clear()


def test_failed_model_partial_decisions_are_not_executed_later(shadow, tmp_path):
    from src.agent.journal import Journal

    journal = Journal(tmp_path / "journal")
    journal.init()
    journal.decisions_file.write_text("original\n")
    turn = claim_turn(shadow.broker)

    def failed_turn():
        journal.decisions_file.write_text("original\npartial failed model decision\n")
        raise TimeoutError

    do_turn(shadow.broker, SimpleNamespace(journal=journal, run_morning_research=failed_turn),
            None, turn, threading.Event())
    assert journal.decisions_file.read_text() == "original\n"
    assert shadow.broker.read()["turns"][0]["status"] == "error"


def test_process_crash_during_model_restores_decisions_without_resetting_budget(shadow, tmp_path):
    from src.agent.journal import Journal
    from src.evals.toss_shadow import recover_interrupted_turns
    from src.execution.brokers.toss import storage

    b = shadow.broker
    journal = Journal(tmp_path / "journal")
    journal.init()
    turn = claim_turn(b)
    storage.write_json(b.root / "turn-backup.json", {"turn_id": turn["id"], "decisions": "before\n"})
    with b.transaction() as state:
        state["turns"][0]["status"] = "started"
    journal.decisions_file.write_text("partial model edits\n")
    recover_interrupted_turns(b, journal)
    assert journal.decisions_file.read_text() == "before\n"
    assert b.read()["turns"][0]["error_type"] == "InterruptedTurn"
    assert claim_turn(b) is None


def test_fee_expiry_while_fetching_books_uses_the_new_rate(shadow, monkeypatch):
    b = shadow.broker
    shadow.now[0] = datetime(2026, 11, 23, 14, 59, 55, tzinfo=UTC)
    shadow.feed["end"] = "2026-11-23"
    b.costs.schedule.get(force=True)
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1))
    request = shadow.client.request

    def slow_book(method, path, **kwargs):
        response = request(method, path, **kwargs)
        if path == "/api/v1/orderbook":
            shadow.now[0] += timedelta(seconds=6)
            shadow.feed.update(rate="0.002", end=None)
        return response

    monkeypatch.setattr(shadow.client, "request", slow_book)
    shadow.advance()
    assert b.get_order_status(placed.order_id).commission == 0.21


def test_quotes_returning_after_market_close_do_not_fill(shadow, monkeypatch):
    b = shadow.broker
    shadow.now[0] = datetime(2026, 11, 23, 20, 59, 55, tzinfo=UTC)
    placed = b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, qty=1))
    request = shadow.client.request

    def slow_book(method, path, **kwargs):
        response = request(method, path, **kwargs)
        if path == "/api/v1/orderbook":
            shadow.now[0] += timedelta(seconds=6)
        return response

    monkeypatch.setattr(shadow.client, "request", slow_book)
    shadow.advance()
    assert b.get_order_status(placed.order_id).qty == 0
    assert not b.get_open_orders()
