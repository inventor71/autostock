"""Market data formatter for LLM context preparation."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from loguru import logger

from src.strategy.ml.feature_eng import build_technical_features

if TYPE_CHECKING:
    from src.data.providers.news_provider import NewsItem


class MarketDataFormatter:
    """Formats market data for LLM consumption.

    Converts OHLCV data, technical indicators, and news into
    a structured text format suitable for LLM context.
    """

    def __init__(self, lookback_days: int = 30, include_news: bool = True):
        self.lookback_days = lookback_days
        self.include_news = include_news

    def format_for_llm(
        self,
        symbol: str,
        bars: pd.DataFrame,
        news: list[NewsItem] | None = None,
    ) -> str:
        """Format market data into LLM-readable context.

        Args:
            symbol: Ticker symbol.
            bars: OHLCV DataFrame with DatetimeIndex.
            news: Optional list of NewsItem objects.

        Returns:
            Formatted string for LLM context.
        """
        bars = self._drop_incomplete_last_bar(bars, symbol)

        sections = [
            f"=== Market Analysis for {symbol} ===",
            f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            self._format_price_summary(bars),
            "",
            self._format_technical_indicators(bars),
            "",
            self._format_price_levels(bars),
            "",
            self._format_volume_analysis(bars),
        ]

        if self.include_news and news:
            sections.append("")
            sections.append(self._format_news(news))

        return "\n".join(sections)

    @staticmethod
    def _drop_incomplete_last_bar(bars: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
        """Drop a trailing in-progress bar so all sections use a completed bar.

        yfinance intraday history includes the current forming bar, whose volume
        is 0 right after a bar boundary. Using it skews current price, volume
        ratio and price-volume analysis, so drop it (keeping at least one bar).
        """
        if len(bars) > 1 and bars.iloc[-1]["volume"] == 0:
            logger.debug(
                f"Dropping incomplete last bar (volume=0) for {symbol or 'symbol'} "
                f"before LLM formatting"
            )
            return bars.iloc[:-1]
        return bars

    def _format_price_summary(self, bars: pd.DataFrame) -> str:
        """Format recent price action summary."""
        recent = bars.tail(self.lookback_days)
        latest = bars.iloc[-1]
        prev = bars.iloc[-2] if len(bars) > 1 else latest

        change_1d = (latest["close"] / prev["close"] - 1) * 100
        change_5d = self._calculate_period_return(bars, 5)
        change_20d = self._calculate_period_return(bars, 20)

        high_period = recent["high"].max()
        low_period = recent["low"].min()
        range_pct = (high_period / low_period - 1) * 100

        lines = [
            "## Price Summary",
            f"Current Price: ${latest['close']:.2f}",
            f"1-Day Change: {change_1d:+.2f}%",
            f"5-Day Change: {change_5d:+.2f}%",
            f"20-Day Change: {change_20d:+.2f}%",
            f"{self.lookback_days}-Day High: ${high_period:.2f}",
            f"{self.lookback_days}-Day Low: ${low_period:.2f}",
            f"Price Range: {range_pct:.1f}%",
        ]
        return "\n".join(lines)

    def _format_technical_indicators(self, bars: pd.DataFrame) -> str:
        """Format technical indicators using feature engineering."""
        try:
            features = build_technical_features(bars)
            if features.empty:
                return "## Technical Indicators\nInsufficient data for technical analysis."

            latest = features.iloc[-1]

            # RSI interpretation
            rsi = latest.get("rsi_14", 50)
            if rsi > 70:
                rsi_signal = "Overbought"
            elif rsi < 30:
                rsi_signal = "Oversold"
            else:
                rsi_signal = "Neutral"

            # MACD interpretation
            macd_hist = latest.get("macd_hist", 0)
            macd_signal = "Bullish" if macd_hist > 0 else "Bearish"

            # Bollinger Bands
            bb_pct = latest.get("bb_pct_b", 0.5)
            if bb_pct > 0.8:
                bb_signal = "Near Upper Band (Potentially Overbought)"
            elif bb_pct < 0.2:
                bb_signal = "Near Lower Band (Potentially Oversold)"
            else:
                bb_signal = "Within Bands"

            # Trend
            price_to_sma20 = latest.get("price_to_sma20", 0) * 100
            price_to_sma50 = latest.get("price_to_sma50", 0) * 100
            sma_cross = latest.get("sma20_to_sma50", 0) * 100

            if sma_cross > 0:
                trend = "Bullish (SMA20 > SMA50)"
            else:
                trend = "Bearish (SMA20 < SMA50)"

            lines = [
                "## Technical Indicators",
                f"RSI (14): {rsi:.1f} - {rsi_signal}",
                f"MACD Histogram: {macd_hist:.4f} - {macd_signal}",
                f"Bollinger %B: {bb_pct:.2f} - {bb_signal}",
                f"Price vs SMA20: {price_to_sma20:+.2f}%",
                f"Price vs SMA50: {price_to_sma50:+.2f}%",
                f"Trend: {trend}",
                f"ATR (14): {latest.get('atr_14', 0) * 100:.2f}% (volatility measure)",
                f"20-Day Volatility: {latest.get('volatility_20d', 0) * 100:.2f}%",
            ]
            return "\n".join(lines)

        except Exception as e:
            return f"## Technical Indicators\nError calculating indicators: {e}"

    def _format_price_levels(self, bars: pd.DataFrame) -> str:
        """Format support and resistance levels."""
        recent = bars.tail(self.lookback_days)
        current_price = bars.iloc[-1]["close"]

        # Simple pivot point calculation
        high = recent["high"].max()
        low = recent["low"].min()
        close = bars.iloc[-1]["close"]
        pivot = (high + low + close) / 3

        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)

        # Find local peaks and troughs
        resistance_levels = self._find_resistance_levels(recent, current_price)
        support_levels = self._find_support_levels(recent, current_price)

        lines = [
            "## Key Price Levels",
            f"Pivot Point: ${pivot:.2f}",
            f"Resistance 1: ${r1:.2f} ({(r1/current_price - 1) * 100:+.1f}%)",
            f"Resistance 2: ${r2:.2f} ({(r2/current_price - 1) * 100:+.1f}%)",
            f"Support 1: ${s1:.2f} ({(s1/current_price - 1) * 100:+.1f}%)",
            f"Support 2: ${s2:.2f} ({(s2/current_price - 1) * 100:+.1f}%)",
        ]

        if resistance_levels:
            lines.append(f"Recent Highs: {', '.join(f'${p:.2f}' for p in resistance_levels[:3])}")
        if support_levels:
            lines.append(f"Recent Lows: {', '.join(f'${p:.2f}' for p in support_levels[:3])}")

        return "\n".join(lines)

    def _format_volume_analysis(self, bars: pd.DataFrame) -> str:
        """Format volume analysis."""
        recent = bars.tail(self.lookback_days)
        latest_vol = bars.iloc[-1]["volume"]
        avg_vol = recent["volume"].mean()
        vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1.0

        # Volume trend
        vol_5d = bars.tail(5)["volume"].mean()
        vol_20d = bars.tail(20)["volume"].mean()
        vol_trend = "Increasing" if vol_5d > vol_20d else "Decreasing"

        # Price-volume relationship
        recent_5 = bars.tail(5)
        price_up = recent_5["close"].iloc[-1] > recent_5["close"].iloc[0]
        vol_up = recent_5["volume"].iloc[-1] > recent_5["volume"].mean()

        if price_up and vol_up:
            pv_signal = "Bullish Confirmation (Price up + Volume up)"
        elif not price_up and vol_up:
            pv_signal = "Bearish Confirmation (Price down + Volume up)"
        elif price_up and not vol_up:
            pv_signal = "Weak Rally (Price up + Low volume)"
        else:
            pv_signal = "Weak Decline (Price down + Low volume)"

        lines = [
            "## Volume Analysis",
            f"Current Volume: {latest_vol:,.0f}",
            f"Average Volume ({self.lookback_days}d): {avg_vol:,.0f}",
            f"Volume Ratio: {vol_ratio:.2f}x average",
            f"Volume Trend: {vol_trend}",
            f"Price-Volume: {pv_signal}",
        ]
        return "\n".join(lines)

    def _format_news(self, news: list[NewsItem]) -> str:
        """Format news headlines."""
        if not news:
            return "## Recent News\nNo recent news available."

        lines = ["## Recent News Headlines"]
        for item in news[:5]:  # Limit to 5 most recent
            sentiment = ""
            if hasattr(item, "sentiment_score") and item.sentiment_score is not None:
                if item.sentiment_score > 0.3:
                    sentiment = " [Positive]"
                elif item.sentiment_score < -0.3:
                    sentiment = " [Negative]"
                else:
                    sentiment = " [Neutral]"

            date_str = item.published_at.strftime("%Y-%m-%d") if item.published_at else "N/A"
            lines.append(f"- [{date_str}] {item.title}{sentiment}")

        return "\n".join(lines)

    def _calculate_period_return(self, bars: pd.DataFrame, days: int) -> float:
        """Calculate return over a specified period."""
        if len(bars) < days + 1:
            return 0.0
        current = bars.iloc[-1]["close"]
        past = bars.iloc[-days - 1]["close"]
        return (current / past - 1) * 100

    def _find_resistance_levels(
        self, bars: pd.DataFrame, current_price: float
    ) -> list[float]:
        """Find resistance levels (local highs) above current price, ascending."""
        return self._find_pivot_levels(bars["high"].values, current_price, "resistance")

    def _find_support_levels(
        self, bars: pd.DataFrame, current_price: float
    ) -> list[float]:
        """Find support levels (local lows) below current price, descending."""
        return self._find_pivot_levels(bars["low"].values, current_price, "support")

    @staticmethod
    def _find_pivot_levels(series, current_price: float, kind: str) -> list[float]:
        """Local pivots with 2 bars confirmation on each side, filtered to one side
        of ``current_price``. ``kind='resistance'`` -> local maxima strictly above,
        ascending; ``kind='support'`` -> local minima strictly below, descending.
        The two are mirror images, so this is the single scan both call sites share."""
        above = kind == "resistance"
        levels = []
        for i in range(2, len(series) - 2):
            v = series[i]
            is_pivot = (
                all(v > series[i + d] for d in (-2, -1, 1, 2))
                if above
                else all(v < series[i + d] for d in (-2, -1, 1, 2))
            )
            if is_pivot and (v > current_price if above else v < current_price):
                levels.append(v)
        return sorted(set(levels), reverse=not above)


def truncate_context(context: str, max_chars: int = 8000) -> str:
    """Truncate context to fit within token limits.

    Args:
        context: Full context string.
        max_chars: Maximum characters (rough token proxy).

    Returns:
        Truncated context with indicator that truncation occurred.
    """
    if len(context) <= max_chars:
        return context

    # Keep essential sections, truncate news/details
    lines = context.split("\n")
    result = []
    current_len = 0

    for line in lines:
        if current_len + len(line) + 1 > max_chars - 50:
            result.append("... [Context truncated for token limit]")
            break
        result.append(line)
        current_len += len(line) + 1

    return "\n".join(result)
