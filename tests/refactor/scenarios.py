"""Shared deterministic scenarios for the R2 speed-review characterization tests.

These build fixed inputs (seeded synthetic bars, fixed strategy/grid) so the
exact numeric output of the backtest engine and optimizer can be frozen as a
golden snapshot. The refactor must keep before/after output identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.backtest.optimizer import ParameterOptimizer
from src.strategy.technical.ma_crossover import MovingAverageCrossover


def make_bars(n: int = 200, base_price: float = 100.0, trend: float = 0.001) -> pd.DataFrame:
    """Seeded synthetic OHLCV — identical to tests/test_backtest.make_bars."""
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


RISK_CONFIG = {"max_position_pct": 0.2, "stop_loss_pct": 0.05, "take_profit_pct": 0.15}
OPT_GRID = {"fast_period": [10, 20], "slow_period": [40, 50]}


def run_engine() -> dict:
    """Deterministic single-symbol backtest → snapshot of the observable result."""
    bars = make_bars(200)
    engine = BacktestEngine(
        strategy=MovingAverageCrossover(params={"fast_period": 10, "slow_period": 30}),
        initial_capital=100_000.0,
        risk_config=RISK_CONFIG,
    )
    result = engine.run("TEST", bars)
    return {
        "final_capital": result.final_capital,
        "total_return_pct": result.total_return_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown_pct": result.max_drawdown_pct,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "equity_curve": [float(x) for x in result.equity_curve],
        "fills": [
            {"symbol": f.symbol, "side": f.side.value, "qty": float(f.qty),
             "price": float(f.filled_price)}
            for f in result.trades
        ],
    }


def run_optimizer() -> dict:
    """Deterministic grid search → snapshot of best + ordered all_results."""
    bars = make_bars(200)
    opt = ParameterOptimizer(
        strategy_class=MovingAverageCrossover,
        param_grid=OPT_GRID,
        initial_capital=100_000.0,
        metric="sharpe_ratio",
    )
    best_params, best_result, all_results = opt.optimize("TEST", bars, risk_config=RISK_CONFIG)
    return {
        "best_params": best_params,
        "best_metric": float(getattr(best_result, "sharpe_ratio", 0.0)),
        "all_results": [
            {"params": r["params"], "metric_value": float(r["metric_value"])}
            for r in all_results
        ],
    }
