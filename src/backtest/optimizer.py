from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from typing import TYPE_CHECKING, Any, Type

import pandas as pd
from loguru import logger

from src.backtest.engine import BacktestEngine
from src.core.models import BacktestResult
from src.strategy.base import BaseStrategy

if TYPE_CHECKING:
    from loguru import Logger


def _run_combo(args: tuple) -> tuple:
    """Run one grid point and return (params, metric_value, result).

    Module-level so it is picklable for ProcessPoolExecutor. ``metric_value`` is
    ``None`` when the combo failed — the caller skips it, mirroring the original
    sequential ``except: continue`` (a failed combo never enters all_results).
    The default logger is used inside the worker (a loguru handle is not passed
    across the process boundary); this affects only logging, not results.
    """
    strategy_class, params, symbol, bars, risk_config, initial_capital, metric = args
    try:
        strategy = strategy_class(params=params)
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=initial_capital,
            risk_config=risk_config,
        )
        result = engine.run(symbol, bars)
        return params, getattr(result, metric, 0.0), result
    except Exception:
        return params, None, None


class ParameterOptimizer:
    """Grid search optimizer for strategy parameters."""

    def __init__(
        self,
        strategy_class: Type[BaseStrategy],
        param_grid: dict[str, list[Any]],
        initial_capital: float = 100000.0,
        metric: str = "sharpe_ratio",
        bt_logger: Logger | None = None,
        max_workers: int | None = None,
    ):
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.initial_capital = initial_capital
        self.metric = metric
        self._logger = bt_logger or logger
        # Grid points are independent → run them in parallel across processes.
        # None ⇒ os.cpu_count(); 1 ⇒ sequential in-process (debug / tiny grids).
        # Behavior is identical to sequential either way: ProcessPoolExecutor.map
        # preserves input (combo) order, and best selection is the same
        # first-max-wins scan over that order.
        self._max_workers = max_workers

    def optimize(
        self,
        symbol: str,
        bars: pd.DataFrame,
        risk_config: dict | None = None,
    ) -> tuple[dict[str, Any], BacktestResult, list[dict]]:
        """Run grid search optimization.

        Returns:
            Tuple of (best_params, best_result, all_results)
        """
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        combinations = list(product(*param_values))

        self._logger.info(
            f"Optimizing {self.strategy_class.__name__}: "
            f"{len(combinations)} parameter combinations"
        )

        tasks = [
            (self.strategy_class, dict(zip(param_names, combo)), symbol, bars,
             risk_config, self.initial_capital, self.metric)
            for combo in combinations
        ]

        workers = self._max_workers if self._max_workers is not None else (os.cpu_count() or 1)
        if workers <= 1 or len(tasks) <= 1:
            computed = [_run_combo(t) for t in tasks]
        else:
            # .map preserves input order, so the downstream first-max-wins scan
            # below produces a result identical to the sequential version.
            with ProcessPoolExecutor(max_workers=workers) as ex:
                computed = list(ex.map(_run_combo, tasks))

        all_results = []
        best_result = None
        best_params = {}
        best_metric_value = float("-inf")

        # Single-threaded selection over the original combo order: a failed combo
        # (metric_value is None) is skipped exactly like the old `except: continue`,
        # and strict `>` keeps first-max-wins tie-breaking deterministic.
        for params, metric_value, result in computed:
            if metric_value is None:
                self._logger.debug(f"Params {params} failed (skipped)")
                continue
            all_results.append({"params": params, "metric_value": metric_value})
            if metric_value > best_metric_value:
                best_metric_value = metric_value
                best_result = result
                best_params = params

        self._logger.info(
            f"Best params: {best_params} -> {self.metric}={best_metric_value:.4f}"
        )

        return best_params, best_result, all_results
