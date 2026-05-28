"""Tests for the unified polled stop/take-profit backup (src/risk/exits.py).

Covers the three callers' shared logic in one place (replacing the duplication
TradingEngine/DecisionExecutor previously had). Includes a property test
(PBT extension, partial mode — PBT-03 invariant) asserting the core safety
invariant: a symbol covered by a resting exchange-side bracket order must never
be re-exited by the polled backup.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.core.models import FilledOrder, Order, Position, PortfolioState
from src.core.types import OrderSide
from src.execution.brokers.simulated import SimulatedBroker
from src.risk.exits import run_polled_exits
from src.risk.manager import RiskManager


# ---------------------------------------------------------------------- #
# Stubs
# ---------------------------------------------------------------------- #


class _StubProvider:
    """Returns a configured price per symbol; records fetched symbols."""

    def __init__(self, prices: dict[str, float] | None = None, default: float = 100.0):
        self.prices = prices or {}
        self.default = default
        self.fetched: list[str] = []

    def get_latest_price(self, symbol: str) -> float:
        self.fetched.append(symbol)
        if symbol in self.prices:
            return self.prices[symbol]
        return self.default


@dataclass
class _RecordingBroker:
    """Minimal broker stub that records submitted exits without filling."""
    submitted: list[Order] = field(default_factory=list)
    next_order_id: int = 0

    def submit_order(self, order: Order) -> FilledOrder:
        self.submitted.append(order)
        self.next_order_id += 1
        from datetime import datetime
        return FilledOrder(
            order_id=f"x-{self.next_order_id}",
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            filled_price=order.limit_price or 0.0,
            filled_at=datetime.now(),
        )


def _position(symbol: str, qty: float, entry: float, current: float) -> Position:
    p = Position(symbol=symbol, qty=qty, avg_entry_price=entry)
    p.update_price(current)
    return p


def _portfolio(*positions: Position, cash: float = 50_000.0, equity: float = 100_000.0) -> PortfolioState:
    return PortfolioState(
        cash=cash, equity=equity, positions={p.symbol: p for p in positions}
    )


# ---------------------------------------------------------------------- #
# Example tests
# ---------------------------------------------------------------------- #


class TestRunPolledExits:
    def test_no_positions_returns_empty(self):
        rm = RiskManager(stop_loss_pct=0.05)
        broker = _RecordingBroker()
        filled = run_polled_exits(rm, broker, _portfolio(), data_provider=_StubProvider())
        assert filled == []
        assert broker.submitted == []

    def test_triggers_stop_loss_full_portfolio(self):
        rm = RiskManager(stop_loss_pct=0.05)
        portfolio = _portfolio(_position("AAPL", 10, entry=100.0, current=100.0))
        # Latest price is below the 5% stop -> backup must fire.
        provider = _StubProvider(prices={"AAPL": 90.0})
        broker = _RecordingBroker()
        filled = run_polled_exits(rm, broker, portfolio, data_provider=provider)
        assert len(filled) == 1
        assert broker.submitted[0].symbol == "AAPL"
        assert broker.submitted[0].side == OrderSide.SELL

    def test_protected_symbols_are_never_exited(self):
        rm = RiskManager(stop_loss_pct=0.05)
        portfolio = _portfolio(_position("AAPL", 10, entry=100.0, current=90.0))
        broker = _RecordingBroker()
        # AAPL is way underwater AND in the protected set -> no order placed.
        filled = run_polled_exits(
            rm, broker, portfolio, data_provider=_StubProvider(),
            protected_symbols={"AAPL"},
        )
        assert filled == []
        assert broker.submitted == []

    def test_symbol_filter_ignores_other_positions(self):
        """When called per-symbol, exits for OTHER positions must be discarded —
        their prices may be stale (only the ticked symbol was refreshed)."""
        rm = RiskManager(stop_loss_pct=0.05)
        # Both positions underwater per their stored prices.
        portfolio = _portfolio(
            _position("AAPL", 10, entry=100.0, current=90.0),
            _position("MSFT", 5,  entry=200.0, current=180.0),
        )
        broker = _RecordingBroker()
        # We only ticked AAPL; even though MSFT's stored price would trigger,
        # the function must filter it out.
        filled = run_polled_exits(
            rm, broker, portfolio, symbol="AAPL", latest_price=90.0,
        )
        assert all(o.symbol == "AAPL" for o in broker.submitted)
        assert len(filled) == 1

    def test_symbol_not_in_portfolio_returns_empty(self):
        rm = RiskManager(stop_loss_pct=0.05)
        portfolio = _portfolio(_position("AAPL", 10, entry=100.0, current=90.0))
        broker = _RecordingBroker()
        filled = run_polled_exits(
            rm, broker, portfolio, symbol="ZZZZ", latest_price=1.0,
        )
        assert filled == []
        assert broker.submitted == []

    def test_latest_price_avoids_provider_fetch(self):
        rm = RiskManager(stop_loss_pct=0.05)
        portfolio = _portfolio(_position("AAPL", 10, entry=100.0, current=100.0))
        provider = _StubProvider()
        broker = _RecordingBroker()
        run_polled_exits(
            rm, broker, portfolio,
            data_provider=provider, symbol="AAPL", latest_price=90.0,
        )
        # latest_price was supplied -> no fetch should have happened.
        assert provider.fetched == []


# ---------------------------------------------------------------------- #
# PBT-03 invariant property test (extension: PBT, partial mode)
# ---------------------------------------------------------------------- #


@st.composite
def _position_strategy(draw, symbol: str) -> Position:
    """Generate a realistic Position: positive entry, current within +/-30% (so
    a stop trigger is plausible but not guaranteed)."""
    entry = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    drift = draw(st.floats(min_value=-0.3, max_value=0.3, allow_nan=False, allow_infinity=False))
    qty = draw(st.integers(min_value=1, max_value=100))
    return _position(symbol, float(qty), entry=entry, current=entry * (1 + drift))


@st.composite
def _portfolio_strategy(draw) -> tuple[PortfolioState, list[str]]:
    """Generate a portfolio with 1-5 distinct symbols."""
    symbols = draw(st.lists(
        st.sampled_from(["AAPL", "MSFT", "GOOG", "TSLA", "NVDA"]),
        min_size=1, max_size=5, unique=True,
    ))
    positions = [draw(_position_strategy(symbol=s)) for s in symbols]
    return _portfolio(*positions), symbols


class TestPolledExitsInvariants:
    """PBT-03: a symbol covered by a resting bracket (in protected_symbols) is
    never re-exited by the polled backup, no matter how underwater it is."""

    @given(p_and_symbols=_portfolio_strategy(), data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_protected_symbols_never_yield_exit_orders(self, p_and_symbols, data):
        portfolio, symbols = p_and_symbols
        # Pick an arbitrary subset of held symbols as "protected".
        protected_list = data.draw(st.lists(
            st.sampled_from(symbols), min_size=0, max_size=len(symbols), unique=True,
        ))
        protected = set(protected_list)

        rm = RiskManager(stop_loss_pct=0.05, take_profit_pct=0.15)
        broker = _RecordingBroker()
        filled = run_polled_exits(
            rm, broker, portfolio,
            data_provider=None,  # prices already on positions; no refresh needed
            protected_symbols=protected,
        )

        # Invariant: NO order — neither submitted nor filled — targets a
        # protected symbol, regardless of how far underwater it is.
        for order in broker.submitted:
            assert order.symbol not in protected, (
                f"protected symbol {order.symbol} got an exit order"
            )
        for f in filled:
            assert f.symbol not in protected


# ---------------------------------------------------------------------- #
# Fail-closed contract for DecisionExecutor
# ---------------------------------------------------------------------- #


class TestExecutorRequiresBracketRiskManager:
    """S-2: the executor used to silently mutate ``risk_manager.use_bracket_orders``
    on the injected object — now it validates the contract at construction."""

    def test_non_bracket_risk_manager_rejected(self, tmp_path):
        from src.agent.executor import DecisionExecutor
        from src.agent.journal import Journal
        rm = RiskManager()  # default: use_bracket_orders=False
        broker = SimulatedBroker(initial_capital=100_000.0)
        with pytest.raises(ValueError, match="use_bracket_orders"):
            DecisionExecutor(
                broker, rm, _StubProvider(),
                journal=Journal(root=tmp_path / "ws"),
                universe=["AAPL"],
            )

    def test_bracket_risk_manager_accepted(self, tmp_path):
        from src.agent.executor import DecisionExecutor
        from src.agent.journal import Journal
        rm = RiskManager(use_bracket_orders=True)
        broker = SimulatedBroker(initial_capital=100_000.0)
        # Should not raise.
        DecisionExecutor(
            broker, rm, _StubProvider(),
            journal=Journal(root=tmp_path / "ws"),
            universe=["AAPL"],
        )
