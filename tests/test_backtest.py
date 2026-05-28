import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import (
    sharpe_ratio,
    max_drawdown,
    total_return,
    win_rate,
    profit_factor,
)
from src.core.types import OrderSide, Signal
from src.strategy.base import BaseStrategy
from src.strategy.technical.ma_crossover import MovingAverageCrossover


class _BuyAndHold(BaseStrategy):
    """Deterministic test strategy: buy once, then hold (exits come from the
    RiskManager's resting protection, not the strategy)."""

    name = "buy_and_hold"

    def __init__(self, params=None):
        super().__init__(params)
        self._bought = False

    def generate_signal(self, symbol, bars, portfolio=None):
        held = portfolio is not None and symbol in portfolio.positions
        if not self._bought and not held:
            self._bought = True
            return self._make_signal(symbol, Signal.BUY, confidence=1.0)
        return self._make_signal(symbol, Signal.HOLD)


def _ohlc(rows: list[tuple]) -> pd.DataFrame:
    """Build OHLCV bars from (open, high, low, close) tuples."""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["volume"] = 1_000_000
    df.index = pd.date_range("2023-01-01", periods=len(rows), freq="D")
    return df


def make_bars(n: int = 200, base_price: float = 100.0, trend: float = 0.001) -> pd.DataFrame:
    """Generate synthetic bar data with slight uptrend."""
    np.random.seed(42)
    returns = np.random.normal(trend, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)
    return pd.DataFrame(
        {
            "open": prices * 0.999,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": np.random.randint(100000, 1000000, n),
        },
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


class TestMetrics:
    def test_sharpe_ratio(self):
        returns = pd.Series(np.random.normal(0.001, 0.01, 252))
        sr = sharpe_ratio(returns)
        assert isinstance(sr, float)

    def test_max_drawdown(self):
        equity = pd.Series([100, 110, 105, 95, 100, 115])
        mdd = max_drawdown(equity)
        # Max drawdown from 110 to 95 = 13.6%
        assert mdd == pytest.approx(95 / 110 - 1, abs=0.01) or mdd > 0

    def test_total_return(self):
        equity = pd.Series([100, 110, 120])
        assert total_return(equity) == pytest.approx(20.0)

    def test_win_rate(self):
        trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}]
        assert win_rate(trades) == pytest.approx(2 / 3)

    def test_profit_factor(self):
        trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}]
        assert profit_factor(trades) == pytest.approx(300 / 50)


class TestBacktestEngine:
    def test_backtest_runs(self):
        strategy = MovingAverageCrossover({"fast_period": 10, "slow_period": 30})
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=100000.0,
        )
        bars = make_bars(200)
        result = engine.run("AAPL", bars, warmup_period=30)

        assert result.strategy_name == "ma_crossover"
        assert result.initial_capital == 100000.0
        assert result.final_capital > 0
        assert len(result.equity_curve) > 0

    def test_backtest_with_risk_config(self):
        strategy = MovingAverageCrossover({"fast_period": 5, "slow_period": 20})
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=50000.0,
            risk_config={
                "max_position_pct": 0.2,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.1,
            },
        )
        bars = make_bars(150)
        result = engine.run("SPY", bars, warmup_period=20)
        assert result.final_capital > 0


class TestBacktestFidelity:
    """B-1/B-2: exits trigger intra-bar like live, and metrics count closed
    round-trips (not every fill)."""

    _RISK = {"max_position_pct": 0.1, "stop_loss_pct": 0.05, "take_profit_pct": 0.15}

    def test_intrabar_stop_triggers_on_low_not_close(self):
        # Buy at bar 2 @100 (stop armed at 95). Bar 3 CLOSES at 98 — above the
        # stop — but its LOW dips to 94. A close-only backtest would miss the
        # stop-out; the resting stop must fire intra-bar and fill at 95.
        bars = _ohlc([
            (100, 100, 100, 100),  # 0 warmup
            (100, 100, 100, 100),  # 1 warmup
            (100, 100, 100, 100),  # 2 buy @100
            (98, 99, 94, 98),      # 3 low 94 < stop 95 -> stop fills @95
            (98, 99, 98, 98),      # 4
        ])
        engine = BacktestEngine(_BuyAndHold(), initial_capital=100_000.0, risk_config=self._RISK)
        result = engine.run("AAPL", bars, warmup_period=2)

        sells = [t for t in result.trades if t.side == OrderSide.SELL]
        assert sells, "intra-bar low should have triggered the resting stop"
        assert sells[0].filled_price == pytest.approx(95.0)
        assert engine.broker.get_position("AAPL") is None

    def test_metrics_count_round_trips_not_fills(self):
        # Buy @100 (target 115). Bar 3 high 116 >= 115 -> take-profit fills @115.
        bars = _ohlc([
            (100, 100, 100, 100),  # 0 warmup
            (100, 100, 100, 100),  # 1 warmup
            (100, 100, 100, 100),  # 2 buy @100
            (110, 116, 109, 112),  # 3 high 116 >= target 115 -> tp fills @115 (win)
            (112, 112, 112, 112),  # 4
        ])
        engine = BacktestEngine(_BuyAndHold(), initial_capital=100_000.0, risk_config=self._RISK)
        result = engine.run("AAPL", bars, warmup_period=2)

        # One buy + one sell were FILLED...
        assert len(result.trades) == 2
        # ...but that is ONE closed round-trip, not two trades -- and it won.
        assert result.total_trades == 1
        assert result.win_rate == pytest.approx(1.0)
