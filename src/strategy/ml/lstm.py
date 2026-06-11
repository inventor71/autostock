from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.core.types import Signal
from src.strategy.ml.base_ml import BaseMLStrategy
from src.strategy.ml.feature_eng import build_technical_features
from src.strategy.registry import register_strategy

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:
    class LSTMModel(nn.Module):
        def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0,
                batch_first=True,
            )
            self.fc = nn.Sequential(
                nn.Linear(hidden_size, 64),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, 3),  # 3 classes: buy, hold, sell
            )

        def forward(self, x):
            lstm_out, _ = self.lstm(x)
            last_hidden = lstm_out[:, -1, :]
            return self.fc(last_hidden)


@register_strategy("lstm")
class LSTMStrategy(BaseMLStrategy):
    """LSTM-based sequence prediction strategy."""

    name = "lstm"

    def __init__(self, params: dict | None = None):
        self.sequence_length = (params or {}).get("sequence_length", 60)
        self.hidden_size = (params or {}).get("hidden_size", 128)
        self.num_layers = (params or {}).get("num_layers", 2)
        self.dropout = (params or {}).get("dropout", 0.2)
        self._input_size = None
        self._device = "cuda" if HAS_TORCH and torch.cuda.is_available() else "cpu"
        super().__init__(params)

    def build_features(self, bars: pd.DataFrame) -> np.ndarray:
        features_df = build_technical_features(bars)
        if len(features_df) < self.sequence_length:
            return np.array([])

        # Normalize features
        values = features_df.values
        mean = values.mean(axis=0)
        std = values.std(axis=0)
        std[std == 0] = 1
        normalized = (values - mean) / std

        return normalized

    def _build_sequences(self, features: np.ndarray) -> np.ndarray:
        """Build sequences of fixed length for LSTM input."""
        sequences = []
        for i in range(self.sequence_length, len(features)):
            sequences.append(features[i - self.sequence_length:i])
        return np.array(sequences) if sequences else np.array([])

    def train(self, bars: pd.DataFrame, labels: np.ndarray | None = None) -> None:
        if not HAS_TORCH:
            raise ImportError("PyTorch required for LSTMStrategy")

        from src.strategy.ml.feature_eng import generate_labels

        features = self.build_features(bars)
        if features.size == 0:
            raise ValueError("Not enough data for LSTM training")

        if labels is None:
            raw_labels = generate_labels(bars)
            # Align with features (features_df drops NaN rows)
            aligned_labels = raw_labels[len(bars) - len(features):]
        else:
            aligned_labels = labels

        sequences = self._build_sequences(features)
        if sequences.size == 0:
            raise ValueError("Not enough data to build sequences")

        # Labels for sequences (offset by sequence_length)
        seq_labels = aligned_labels[self.sequence_length:]
        seq_labels = seq_labels[:len(sequences)]

        # Map labels: -1->0, 0->1, 1->2
        label_map = {-1: 0, 0: 1, 1: 2}
        mapped_labels = np.array([label_map.get(int(l), 1) for l in seq_labels])

        self._input_size = features.shape[1]
        self.model = LSTMModel(
            input_size=self._input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
        ).to(self._device)

        X = torch.FloatTensor(sequences).to(self._device)
        y = torch.LongTensor(mapped_labels).to(self._device)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss()

        self.model.train()
        epochs = self.params.get("epochs", 50)
        for epoch in range(epochs):
            optimizer.zero_grad()
            output = self.model(X)
            loss = criterion(output, y)
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 10 == 0:
                logger.debug(f"LSTM epoch {epoch+1}/{epochs}, loss={loss.item():.4f}")

        logger.info(f"LSTM training complete: {len(sequences)} sequences")

    def predict(self, features: np.ndarray) -> tuple[Signal, float]:
        if not HAS_TORCH or self.model is None:
            return Signal.HOLD, 0.0

        # Build sequence from latest features
        if len(features) < self.sequence_length:
            return Signal.HOLD, 0.0

        sequence = features[-self.sequence_length:]
        X = torch.FloatTensor(sequence).unsqueeze(0).to(self._device)

        self.model.eval()
        with torch.no_grad():
            output = self.model(X)
            probs = torch.softmax(output, dim=1)[0]

        predicted_class = torch.argmax(probs).item()
        confidence = float(probs[predicted_class])

        # Map back: 0->SELL, 1->HOLD, 2->BUY
        signal_map = {0: Signal.SELL, 1: Signal.HOLD, 2: Signal.BUY}
        return signal_map[predicted_class], confidence

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio=None,
    ) -> Any:
        """Override to use full feature sequence for LSTM."""
        if self.model is None:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        features = self.build_features(bars)
        if features.size == 0 or len(features) < self.sequence_length:
            return self._make_signal(symbol, Signal.HOLD, confidence=0.0)

        signal, confidence = self.predict(features)
        return self._make_signal(symbol, signal, confidence)

    def save_model(self, path: str | Path) -> None:
        if not HAS_TORCH or self.model is None:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state": self.model.state_dict(),
            "input_size": self._input_size,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
        }, path)
        logger.info(f"Saved LSTM model to {path}")

    def load_model(self, path: str | Path) -> Any:
        if not HAS_TORCH:
            return None
        checkpoint = torch.load(path, map_location=self._device)
        self._input_size = checkpoint["input_size"]
        model = LSTMModel(
            input_size=self._input_size,
            hidden_size=checkpoint["hidden_size"],
            num_layers=checkpoint["num_layers"],
            dropout=checkpoint["dropout"],
        ).to(self._device)
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        return model
