from __future__ import annotations

from collections import Counter

import pandas as pd
from loguru import logger

from src.core.exceptions import InsufficientDataError
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy


@register_strategy("voting_ensemble")
class VotingEnsemble(BaseStrategy):
    """Majority voting ensemble strategy.

    Combines multiple strategy signals using simple or weighted voting.
    """

    name = "voting_ensemble"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.strategies: list[BaseStrategy] = []
        self.min_agreement = self.params.get("min_agreement", 0.6)

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self.strategies.append(strategy)

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        if not self.strategies:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        signals = []
        for strategy in self.strategies:
            try:
                sig = strategy.generate_signal(symbol, bars, portfolio)
                signals.append(sig)
            except InsufficientDataError:
                continue
            except Exception as e:
                logger.debug(f"Ensemble: {strategy.name} failed: {e}")
                continue

        if not signals:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        # Count votes
        votes = Counter(s.signal for s in signals)
        total_votes = len(signals)

        # Determine winner
        most_common_signal, count = votes.most_common(1)[0]
        agreement = count / total_votes

        if agreement >= self.min_agreement and most_common_signal != Signal.HOLD:
            # Average confidence of agreeing strategies
            avg_confidence = sum(
                s.confidence for s in signals if s.signal == most_common_signal
            ) / count
            confidence = avg_confidence * agreement
        else:
            most_common_signal = Signal.HOLD
            confidence = 0.3

        logger.debug(
            f"{symbol} Ensemble votes: {dict(votes)}, "
            f"agreement={agreement:.1%} -> {most_common_signal.value}"
        )

        return self._make_signal(
            symbol=symbol,
            signal=most_common_signal,
            confidence=confidence,
            metadata={"votes": dict(votes), "agreement": agreement},
        )
