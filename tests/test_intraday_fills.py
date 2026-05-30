"""Step 2 — broker ``get_fills`` (activities feed, Q3=A / critic#3).

Simulated brokers no-op; AlpacaBroker parses raw ``/account/activities`` and is
idempotent by activity id. Live shape is verified separately (R1, manual).
"""

from __future__ import annotations

import src.execution.brokers.alpaca_broker as alpaca_broker
from src.execution.brokers.alpaca_broker import AlpacaBroker
from src.execution.brokers.simulated import SimulatedBroker


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
