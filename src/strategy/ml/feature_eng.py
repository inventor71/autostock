from __future__ import annotations

import numpy as np
import pandas as pd
import ta


def build_technical_features(bars: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Build a comprehensive feature set from OHLCV data.

    Features include:
    - Returns (1-day, 5-day, 20-day)
    - Volatility (rolling std)
    - RSI
    - MACD components
    - Bollinger Band %B
    - Volume features
    - Moving average ratios
    """
    df = pd.DataFrame(index=bars.index)
    close = bars["close"]
    volume = bars["volume"]

    # Returns
    df["return_1d"] = close.pct_change(1)
    df["return_5d"] = close.pct_change(5)
    df["return_20d"] = close.pct_change(20)

    # Volatility
    df["volatility_20d"] = close.pct_change().rolling(20).std()

    # RSI
    df["rsi_14"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    # MACD
    macd = ta.trend.MACD(close)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    upper = bb.bollinger_hband()
    lower = bb.bollinger_lband()
    band_width = upper - lower
    df["bb_pct_b"] = np.where(band_width > 0, (close - lower) / band_width, 0.5)
    df["bb_width"] = band_width / close

    # Moving average ratios
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    df["price_to_sma20"] = close / sma_20 - 1
    df["price_to_sma50"] = close / sma_50 - 1
    df["sma20_to_sma50"] = sma_20 / sma_50 - 1

    # Volume features
    vol_sma = volume.rolling(20).mean()
    df["volume_ratio"] = np.where(vol_sma > 0, volume / vol_sma, 1.0)
    df["volume_change"] = volume.pct_change()

    # ATR
    df["atr_14"] = ta.volatility.AverageTrueRange(
        bars["high"], bars["low"], close, window=14
    ).average_true_range() / close

    return df.dropna()


def generate_labels(
    bars: pd.DataFrame,
    forward_period: int = 5,
    threshold: float = 0.02,
) -> np.ndarray:
    """Generate classification labels based on forward returns.

    Args:
        bars: OHLCV DataFrame.
        forward_period: Number of days to look ahead.
        threshold: Minimum return to classify as buy/sell.

    Returns:
        Array of labels: 1 (buy), -1 (sell), 0 (hold).
    """
    close = bars["close"]
    forward_return = close.shift(-forward_period) / close - 1

    labels = np.zeros(len(bars))
    labels[forward_return > threshold] = 1
    labels[forward_return < -threshold] = -1

    return labels
