from __future__ import annotations

import pandas as pd
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("weighted_ensemble")
class WeightedEnsemble(BaseStrategy):
    """Weighted ensemble strategy.

    Each sub-strategy has an assigned weight. The final signal is
    determined by the weighted sum of signals.
    """

    name = "weighted_ensemble"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.strategies: list[tuple[BaseStrategy, float]] = []
        self.buy_threshold = self.params.get("buy_threshold", 0.3)
        self.sell_threshold = self.params.get("sell_threshold", -0.3)

    def add_strategy(self, strategy: BaseStrategy, weight: float) -> None:
        self.strategies.append((strategy, weight))

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        if not self.strategies:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        total_weight = 0.0
        weighted_score = 0.0

        for strategy, weight in self.strategies:
            try:
                sig = strategy.generate_signal(symbol, bars, portfolio)
            except InsufficientDataError:
                continue
            except Exception as e:
                logger.debug(f"Weighted ensemble: {strategy.name} failed: {e}")
                continue

            # Convert signal to numeric: BUY=+1, SELL=-1, HOLD=0
            signal_value = {Signal.BUY: 1.0, Signal.SELL: -1.0, Signal.HOLD: 0.0}
            score = signal_value[sig.signal] * sig.confidence * weight
            weighted_score += score
            total_weight += weight

        if total_weight == 0:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        # Normalize
        normalized_score = weighted_score / total_weight

        if normalized_score > self.buy_threshold:
            signal = Signal.BUY
            confidence = min(abs(normalized_score), 1.0)
        elif normalized_score < self.sell_threshold:
            signal = Signal.SELL
            confidence = min(abs(normalized_score), 1.0)
        else:
            signal = Signal.HOLD
            confidence = 0.3

        logger.debug(
            f"{symbol} Weighted ensemble: score={normalized_score:.3f} -> {signal.value}"
        )

        return self._make_signal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            metadata={"weighted_score": normalized_score},
        )
