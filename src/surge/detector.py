"""EOD surge/dive detector.

Scans the trading universe after market close and identifies stocks
whose daily return exceeded the configured threshold.
"""

from datetime import date, datetime, timedelta

from loguru import logger

from src.data.base import BaseDataProvider
from src.surge.records import SurgeRecord
from src.surge.settings import SurgeDetectionConfig


class SurgeDetector:
    """Detect stocks that surged or dived beyond a threshold."""

    def __init__(
        self,
        provider: BaseDataProvider,
        config: SurgeDetectionConfig | None = None,
    ):
        self.provider = provider
        self.config = config or SurgeDetectionConfig()

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def scan(
        self,
        universe: list[str],
        today: date | None = None,
    ) -> list[SurgeRecord]:
        """Scan the universe for surge/dive stocks.

        Returns records sorted by ``abs(change_pct)`` descending.
        """
        today = today or date.today()
        results: list[SurgeRecord] = []

        for symbol in universe:
            try:
                record = self._scan_one(symbol, today)
                if record is not None:
                    results.append(record)
            except Exception:
                logger.exception(
                    f"surge detector: unexpected error for {symbol}, skipping"
                )

        results.sort(key=lambda r: abs(r.change_pct), reverse=True)
        return results

    # ------------------------------------------------------------------
    # per-symbol
    # ------------------------------------------------------------------

    def _scan_one(self, symbol: str, today: date) -> SurgeRecord | None:
        """Scan a single symbol.  Returns ``None`` when data is unavailable
        or the move is below threshold."""
        bar = self.provider.get_daily_bar(symbol, today)
        if bar is None:
            logger.warning(f"surge detector: no daily bar for {symbol} on {today}")
            return None

        close_today = bar["close"]
        close_prev = bar.get("prev_close")
        if close_prev is None or close_prev <= 0:
            logger.warning(
                f"surge detector: no valid prev_close for {symbol} on {today}"
            )
            return None

        change_pct = self._calculate_change(close_today, close_prev)

        if abs(change_pct) < self.config.threshold_pct:
            return None

        volume = bar.get("volume", 0)
        avg_vol = self._avg_volume(symbol, today)
        volume_ratio = volume / avg_vol if avg_vol > 0 else 0.0

        return SurgeRecord(
            symbol=symbol,
            trading_date=today,
            direction="up" if change_pct > 0 else "down",
            close_prev=close_prev,
            close_today=close_today,
            change_pct=round(change_pct, 2),
            volume=volume,
            avg_volume_20d=avg_vol,
            volume_ratio=round(volume_ratio, 2),
            high_today=bar.get("high", close_today),
            low_today=bar.get("low", close_today),
        )

    # ------------------------------------------------------------------
    # pure helpers (testable with Hypothesis)
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_change(close_today: float, close_prev: float) -> float:
        """Percent change from previous close to today's close.

        Pure function — suitable for property-based testing.
        """
        return (close_today - close_prev) / close_prev * 100

    def _avg_volume(self, symbol: str, today: date) -> int:
        """20-day average volume ending on *today* (inclusive)."""
        start = today - timedelta(days=40)  # generous window for trading days
        df = self.provider.get_bars(symbol, start=start, end=today, limit=30)
        if df.empty or "volume" not in df.columns:
            return 0
        vols = df["volume"].tail(20)
        if vols.empty:
            return 0
        return int(vols.mean())
