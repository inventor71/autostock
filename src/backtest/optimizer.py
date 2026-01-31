from __future__ import annotations

import logging
from itertools import product
from typing import Any, Type

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.core.models import BacktestResult
from src.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """Grid search optimizer for strategy parameters."""

    def __init__(
        self,
        strategy_class: Type[BaseStrategy],
        param_grid: dict[str, list[Any]],
        initial_capital: float = 100000.0,
        metric: str = "sharpe_ratio",
        bt_logger: logging.Logger | None = None,
    ):
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.initial_capital = initial_capital
        self.metric = metric
        self._logger = bt_logger or logger

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

        all_results = []
        best_result = None
        best_params = {}
        best_metric_value = float("-inf")

        for combo in combinations:
            params = dict(zip(param_names, combo))

            try:
                strategy = self.strategy_class(params=params)
                engine = BacktestEngine(
                    strategy=strategy,
                    initial_capital=self.initial_capital,
                    risk_config=risk_config,
                    bt_logger=self._logger,
                )
                result = engine.run(symbol, bars)

                metric_value = getattr(result, self.metric, 0.0)
                all_results.append({
                    "params": params,
                    "metric_value": metric_value,
                })

                if metric_value > best_metric_value:
                    best_metric_value = metric_value
                    best_result = result
                    best_params = params

            except Exception as e:
                self._logger.debug(f"Params {params} failed: {e}")
                continue

        self._logger.info(
            f"Best params: {best_params} -> {self.metric}={best_metric_value:.4f}"
        )

        return best_params, best_result, all_results
