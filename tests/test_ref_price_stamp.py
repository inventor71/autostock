"""F96 — decision-time ``ref_price`` stamping (orchestrator).

The drift guard needs the price the agent decided at as the anchor for a market
entry. The orchestrator stamps it between turns (right after the LLM wrote the
line, before execution) onto BUY/SELL_SHORT decisions that carry no ``limit``.
Everything else — limit entries, exits, holds — is left untouched, and any fetch
failure is swallowed (the guard then simply doesn't apply).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agent.journal import Decision
from src.agent.orchestrator import AgentTradingLoop
from src.agent.session import AgentSession


def _loop(tmp_path, price_provider=None):
    session = AgentSession(workspace=tmp_path, runner=lambda *a, **k: None,
                           session_date=date(2026, 6, 1))
    return AgentTradingLoop(session=session, universe=["AAPL"], price_provider=price_provider)


def test_stamps_market_entries_only(tmp_path):
    loop = _loop(tmp_path, price_provider=lambda sym: 100.0)
    decisions = [
        Decision(symbol="AAPL", action="BUY"),                       # market buy -> stamp
        Decision(symbol="MSFT", action="BUY", limit=95.0),           # limit buy  -> anchor is limit
        Decision(symbol="TSLA", action="SELL_SHORT"),                # market short -> stamp
        Decision(symbol="NVDA", action="SELL", sell_pct=1.0),        # exit -> no anchor needed
        Decision(symbol="AMD", action="HOLD"),                       # hold -> not an entry
    ]
    loop._stamp_ref_prices(decisions)
    assert decisions[0].ref_price == 100.0
    assert decisions[1].ref_price is None
    assert decisions[2].ref_price == 100.0
    assert decisions[3].ref_price is None
    assert decisions[4].ref_price is None


def test_no_provider_is_noop(tmp_path):
    loop = _loop(tmp_path, price_provider=None)
    d = Decision(symbol="AAPL", action="BUY")
    loop._stamp_ref_prices([d])
    assert d.ref_price is None


def test_fetch_error_is_failhonest(tmp_path):
    def boom(sym):
        raise RuntimeError("price feed down")

    loop = _loop(tmp_path, price_provider=boom)
    d = Decision(symbol="AAPL", action="BUY")
    loop._stamp_ref_prices([d])   # must not raise
    assert d.ref_price is None


@pytest.mark.parametrize("bad", [None, 0.0, -3.0])
def test_non_positive_price_not_stamped(tmp_path, bad):
    loop = _loop(tmp_path, price_provider=lambda sym: bad)
    d = Decision(symbol="AAPL", action="BUY")
    loop._stamp_ref_prices([d])
    assert d.ref_price is None


def test_existing_ref_price_not_overwritten(tmp_path):
    loop = _loop(tmp_path, price_provider=lambda sym: 999.0)
    d = Decision(symbol="AAPL", action="BUY", ref_price=100.0)
    loop._stamp_ref_prices([d])
    assert d.ref_price == 100.0
