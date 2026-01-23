from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy


class BaseMLStrategy(BaseStrategy):
    """Abstract base class for ML-based trading strategies.

    Extends BaseStrategy with model training, prediction, and feature
    engineering interfaces.
    """

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.model = None
        self._model_path = self.params.get("model_path")
        if self._model_path:
            self._try_load_model()

    @abstractmethod
    def build_features(self, bars: pd.DataFrame) -> np.ndarray:
        """Build feature matrix from bar data.

        Args:
            bars: OHLCV DataFrame.

        Returns:
            Feature array of shape (n_samples, n_features).
        """
        pass

    @abstractmethod
    def train(self, bars: pd.DataFrame, labels: np.ndarray) -> None:
        """Train the model on historical data.

        Args:
            bars: OHLCV DataFrame for training.
            labels: Target labels (1=buy, -1=sell, 0=hold).
        """
        pass

    @abstractmethod
    def predict(self, features: np.ndarray) -> tuple[Signal, float]:
        """Make prediction from features.

        Returns:
            Tuple of (signal, confidence).
        """
        pass

    @abstractmethod
    def save_model(self, path: str | Path) -> None:
        """Save trained model to disk."""
        pass

    @abstractmethod
    def load_model(self, path: str | Path) -> Any:
        """Load model from disk."""
        pass

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        if self.model is None:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        features = self.build_features(bars)
        if features.size == 0:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        # Use the last row of features for prediction
        latest_features = features[-1:] if features.ndim == 2 else features.reshape(1, -1)
        signal, confidence = self.predict(latest_features)

        logger.debug(f"{symbol} {self.name}: predicted {signal.value} ({confidence:.2f})")

        return self._make_signal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
        )

    def _try_load_model(self) -> None:
        if self._model_path and Path(self._model_path).exists():
            try:
                self.model = self.load_model(self._model_path)
                logger.info(f"Loaded model from {self._model_path}")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
