"""Step 2 — broker ``get_fills`` (activities feed, Q3=A / critic#3).

Simulated brokers no-op; AlpacaBroker parses raw ``/account/activities`` and is
idempotent by activity id. Live shape is verified separately (R1, manual).
"""

from __future__ import annotations

import src.execution.brokers.alpaca_broker as alpaca_broker
from src.execution.brokers.alpaca_broker import AlpacaBroker
from src.execution.brokers.simulated_broker import SimulatedBroker


class _FakeClient:
    """Captures the raw GET path/params and returns a canned activities list."""

    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple[str, dict]] = []

    def get(self, path, data=None):
        self.calls.append((path, data or {}))
        return self._rows


def test_simulated_get_fills_is_noop():
    assert SimulatedBroker().get_fills() == []
    assert SimulatedBroker().get_fills(since="2026-05-30T00:00:00Z") == []


def _alpaca():
    return AlpacaBroker(api_key="x", secret_key="y", paper=True)


def test_alpaca_get_fills_parses_and_filters():
    rows = [
        {"id": "a1", "symbol": "meta", "qty": "50", "price": "631.2",
         "side": "buy", "transaction_time": "2026-05-30T14:31:00Z"},
        {"id": "a2", "symbol": "AAPL", "qty": "10", "price": "200.0",
         "side": "sell", "transaction_time": "2026-05-30T15:00:00Z"},
        {"id": "bad", "symbol": "AAPL", "qty": "1", "price": "1",
         "side": "", "transaction_time": "2026-05-30T15:01:00Z"},  # dropped
    ]
    broker = _alpaca()
    broker._client = _FakeClient(rows)
    fills = broker.get_fills()
    assert [f.fill_id for f in fills] == ["a1", "a2"]
    assert fills[0].symbol == "META" and fills[0].qty == 50.0 and fills[0].side == "buy"
    # request shape: activity_types=FILL, no /v2 prefix
    path, params = broker._client.calls[0]
    assert path == "/account/activities" and params["activity_types"] == "FILL"


def test_alpaca_get_fills_passes_since_as_after():
    broker = _alpaca()
    broker._client = _FakeClient([])
    broker.get_fills(since="2026-05-30T14:00:00Z")
    _, params = broker._client.calls[0]
    assert params.get("after") == "2026-05-30T14:00:00Z"


def test_alpaca_get_fills_failure_returns_empty(monkeypatch):
    broker = _alpaca()

    class _Dead:
        def get(self, *a, **k):
            raise RuntimeError("boom")

    broker._client = _Dead()
    assert broker.get_fills() == []  # best-effort, never raises (NFR-4)


def test_alpaca_get_fills_parses_real_activities_shape():
    # Locked from the live paper /account/activities response (R1, 2026-05-30):
    # ids are "<seq>::<uuid>" (unique even for partial_fill), extra fields present.
    rows = [
        {"id": "20260528094153519::ee11cbd4-b047-4c72-a58a-342e97bb78ac",
         "activity_type": "FILL", "transaction_time": "2026-05-28T13:41:53.519257Z",
         "type": "fill", "side": "buy", "symbol": "META", "qty": "5", "price": "629.91",
         "cum_qty": "5", "leaves_qty": "0", "order_id": "x", "order_status": "filled"},
        {"id": "20260527093702122::00653c7b-c221-4a6f-b8fd-368ac90b0f2f",
         "activity_type": "FILL", "transaction_time": "2026-05-27T13:37:02.122775Z",
         "type": "partial_fill", "side": "buy", "symbol": "RTX", "qty": "19", "price": "176.34",
         "cum_qty": "19", "leaves_qty": "5", "order_id": "y", "order_status": "partially_filled"},
    ]
    broker = _alpaca()
    broker._client = _FakeClient(rows)
    fills = broker.get_fills()
    assert len(fills) == 2
    assert fills[0].fill_id.endswith("ee11cbd4-b047-4c72-a58a-342e97bb78ac")
    assert fills[0].symbol == "META" and fills[0].qty == 5.0 and fills[0].price == 629.91
    # partial_fill keeps its own distinct activity id (idempotency is by id, not order)
    assert fills[1].symbol == "RTX" and fills[1].fill_id != fills[0].fill_id


def test_to_fill_event_fallback_ts_is_tz_aware():
    # No transaction_time -> fallback must be tz-aware so a mixed batch never
    # raises on max(f.ts) in the snapshot cursor (review #3).
    ev = AlpacaBroker._to_fill_event(
        {"id": "x", "symbol": "AAPL", "qty": "1", "price": "1", "side": "buy"})
    assert ev is not None and ev.ts.tzinfo is not None


def test_get_fills_mixed_missing_and_present_transaction_time():
    rows = [
        {"id": "a1", "symbol": "AAPL", "qty": "1", "price": "1", "side": "buy",
         "transaction_time": "2026-05-30T14:31:00Z"},
        {"id": "a2", "symbol": "AAPL", "qty": "1", "price": "1", "side": "buy"},  # no ts
    ]
    broker = _alpaca()
    broker._client = _FakeClient(rows)
    fills = broker.get_fills()
    # both parse, both tz-aware -> max(f.ts) is safe
    assert len(fills) == 2 and all(f.ts.tzinfo is not None for f in fills)
    assert max(f.ts for f in fills)  # does not raise


def test_fill_event_idempotent_by_activity_id():
    # The same order partially filling twice yields two distinct activity ids,
    # so they must NOT collapse (the order-level _alpaca_fills bug this replaces).
    rows = [
        {"id": "p1", "symbol": "AAPL", "qty": "5", "price": "200",
         "side": "buy", "transaction_time": "2026-05-30T14:31:00Z"},
        {"id": "p2", "symbol": "AAPL", "qty": "5", "price": "200.1",
         "side": "buy", "transaction_time": "2026-05-30T14:31:00Z"},
    ]
    broker = _alpaca()
    broker._client = _FakeClient(rows)
    fills = broker.get_fills()
    assert {f.fill_id for f in fills} == {"p1", "p2"}
