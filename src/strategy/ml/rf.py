from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.core.types import Signal
from src.strategy.ml.base_ml import BaseMLStrategy
from src.strategy.ml.feature_eng import build_technical_features, generate_labels
from src.strategy.registry import register_strategy

try:
    from sklearn.ensemble import RandomForestClassifier
except ImportError:
    RandomForestClassifier = None


@register_strategy("random_forest")
class RandomForestStrategy(BaseMLStrategy):
    """Random Forest classification strategy."""

    name = "random_forest"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.n_estimators = self.params.get("n_estimators", 100)
        self.lookback_period = self.params.get("lookback_period", 60)
        self.feature_window = self.params.get("feature_window", 20)

    def build_features(self, bars: pd.DataFrame) -> np.ndarray:
        features_df = build_technical_features(bars, window=self.feature_window)
        return features_df.values

    def train(self, bars: pd.DataFrame, labels: np.ndarray | None = None) -> None:
        if RandomForestClassifier is None:
            raise ImportError("scikit-learn required for RandomForestStrategy")

        features_df = build_technical_features(bars, window=self.feature_window)

        if labels is None:
            labels = generate_labels(bars)

        # Align labels with features (features drop NaN rows)
        aligned_labels = labels[len(bars) - len(features_df):]

        # Remove forward-looking NaN labels
        valid_mask = ~np.isnan(aligned_labels) if np.issubdtype(aligned_labels.dtype, np.floating) else np.ones(len(aligned_labels), dtype=bool)
        X = features_df.values[valid_mask]
        y = aligned_labels[valid_mask]

        if len(X) == 0:
            raise ValueError("No valid training samples")

        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X, y)
        logger.info(f"Trained RF model on {len(X)} samples, {X.shape[1]} features")

    def predict(self, features: np.ndarray) -> tuple[Signal, float]:
        if self.model is None:
            return Signal.HOLD, 0.0

        prediction = self.model.predict(features)[0]
        probas = self.model.predict_proba(features)[0]
        confidence = float(max(probas))

        if prediction == 1:
            return Signal.BUY, confidence
        elif prediction == -1:
            return Signal.SELL, confidence
        else:
            return Signal.HOLD, confidence

    def save_model(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.model, f)
        logger.info(f"Saved RF model to {path}")

    def load_model(self, path: str | Path) -> Any:
        with open(path, "rb") as f:
            model = pickle.load(f)
        return model
