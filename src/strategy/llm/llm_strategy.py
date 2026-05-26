"""LLM-based trading strategy."""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
from loguru import logger

from config.config import get_settings
from src.core.models import PortfolioState, TradeSignal
from src.core.types import Signal
from src.strategy.base import BaseStrategy
from src.strategy.registry import register_strategy
from src.strategy.llm.client import BaseLLMClient, create_llm_client
from src.strategy.llm.data_formatter import MarketDataFormatter, truncate_context


@register_strategy("llm")
class LLMStrategy(BaseStrategy):
    """Trading strategy powered by LLM analysis.

    Uses an LLM (Claude or OpenAI) to analyze market data and generate
    trading signals based on technical analysis.
    """

    name = "llm"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._settings = get_settings()

        # Get provider-specific settings
        self.provider = self.params.get("provider", self._settings.llm.provider)
        self.model = self.params.get("model", self._settings.llm.model)
        self.temperature = self.params.get("temperature", self._settings.llm.temperature)
        self.prompt_version = self.params.get("prompt_version", self._settings.llm.prompt_version)
        self.lookback_days = self.params.get("lookback_days", self._settings.llm.lookback_days)
        self.include_news = self.params.get("include_news", self._settings.llm.include_news)

        # Initialize components lazily
        self._client: BaseLLMClient | None = None
        self._formatter: MarketDataFormatter | None = None
        self._prompt_manager = None
        self._news_provider = None
        self._system_prompt: str | None = None

    @property
    def client(self) -> BaseLLMClient:
        """Lazy initialization of LLM client."""
        if self._client is None:
            api_key = self._get_api_key()
            self._client = create_llm_client(
                provider=self.provider,
                api_key=api_key,
                model=self.model,
                temperature=self.temperature,
            )
            logger.info(f"Initialized {self.provider} LLM client with model {self._client.model}")
        return self._client

    @property
    def formatter(self) -> MarketDataFormatter:
        """Lazy initialization of data formatter."""
        if self._formatter is None:
            self._formatter = MarketDataFormatter(
                lookback_days=self.lookback_days,
                include_news=self.include_news,
            )
        return self._formatter

    @property
    def system_prompt(self) -> str:
        """Load trading prompt from file or prompt manager."""
        if self._system_prompt is None:
            self._system_prompt = self._load_prompt()
        return self._system_prompt

    def _get_api_key(self) -> str:
        """Get API key based on provider."""
        if self.provider == "claude":
            return self._settings.anthropic_api_key
        elif self.provider == "openai":
            return self._settings.openai_api_key
        elif self.provider == "claude_code":
            return ""  # auth comes from the logged-in Claude Code CLI session
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _load_prompt(self) -> str:
        """Load trading prompt from prompt manager or file."""
        try:
            from src.strategy.llm.prompt_manager import PromptManager
            if self._prompt_manager is None:
                self._prompt_manager = PromptManager()
            prompt = self._prompt_manager.get_prompt(self.prompt_version)
            if prompt:
                return prompt.content
        except Exception as e:
            logger.debug(f"PromptManager not available, falling back to file: {e}")

        # Fallback to direct file load
        from pathlib import Path
        prompt_file = Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "trading_prompt_v1.txt"
        if prompt_file.exists():
            return prompt_file.read_text()
        else:
            logger.warning(f"Prompt file not found: {prompt_file}")
            return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Return minimal default prompt if file not found."""
        return """You are a trading analyst. Analyze the market data and respond with JSON only:
{"signal": "BUY" | "SELL" | "HOLD", "confidence": 0.0-1.0, "reasoning": "brief explanation"}"""

    def generate_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        portfolio: PortfolioState | None = None,
    ) -> TradeSignal:
        """Generate trading signal using LLM analysis.

        Args:
            symbol: Ticker symbol.
            bars: OHLCV DataFrame with at least 50 bars.
            portfolio: Current portfolio state (optional).

        Returns:
            TradeSignal with LLM-generated signal and confidence.
        """
        try:
            # Format market data for LLM
            news = self._get_news(symbol) if self.include_news else None
            self._log_news(symbol, news)
            context = self.formatter.format_for_llm(symbol, bars, news)
            context = truncate_context(context)

            # Add portfolio context if available
            if portfolio:
                context += self._format_portfolio_context(symbol, portfolio)

            # Log the full context sent to the LLM for debugging
            logger.debug(
                "LLM request for {} ({} provider, model {}):\n"
                "----- SYSTEM PROMPT -----\n{}\n"
                "----- USER MESSAGE ({} chars) -----\n{}\n"
                "----- END -----",
                symbol,
                self.provider,
                self.model,
                self.system_prompt,
                len(context),
                context,
            )

            # Call LLM API
            response_text = self.client.complete(
                system_prompt=self.system_prompt,
                user_message=context,
            )

            # Parse response
            signal_data = self._parse_llm_response(response_text)

            signal = Signal(signal_data["signal"])
            confidence = float(signal_data.get("confidence", 0.5))
            sell_pct = float(signal_data.get("sell_pct", 1.0))
            # Clamp sell_pct to valid range
            sell_pct = max(0.0, min(1.0, sell_pct))

            metadata = {
                "reasoning": signal_data.get("reasoning", ""),
                "key_levels": signal_data.get("key_levels", {}),
                "risks": signal_data.get("risks", []),
                "llm_provider": self.provider,
                "prompt_version": self.prompt_version,
            }

            logger.debug(
                f"LLM signal for {symbol}: {signal.value} "
                f"(confidence: {confidence:.2f}, sell_pct: {sell_pct:.0%}) - "
                f"{metadata['reasoning'][:500]}..."
            )

            return self._make_signal(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                sell_pct=sell_pct,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"LLM strategy error for {symbol}: {e}")
            return self._make_signal(
                symbol=symbol,
                signal=Signal.HOLD,
                confidence=0.0,
                metadata={"error": str(e)},
            )

    def _get_news(self, symbol: str) -> list | None:
        """Get news for symbol if news provider is available."""
        try:
            if self._news_provider is None:
                from src.data.providers.news_provider import YFinanceNewsProvider
                self._news_provider = YFinanceNewsProvider()
            return self._news_provider.get_news(symbol, limit=5)
        except Exception as e:
            logger.debug(f"Could not fetch news for {symbol}: {e}")
            return None

    def _log_news(self, symbol: str, news: list | None) -> None:
        """Log fetched news items for debugging."""
        if not self.include_news:
            return
        if not news:
            logger.debug(f"No news items for {symbol}")
            return

        lines = [f"Fetched {len(news)} news items for {symbol}:"]
        for i, item in enumerate(news, 1):
            date_str = (
                item.published_at.strftime("%Y-%m-%d %H:%M")
                if getattr(item, "published_at", None)
                else "N/A"
            )
            sentiment = getattr(item, "sentiment_score", None)
            sentiment_str = f"{sentiment:+.2f}" if sentiment is not None else "n/a"
            publisher = getattr(item, "publisher", "") or "unknown"
            lines.append(
                f"  {i}. [{date_str}] ({publisher}, sentiment={sentiment_str}) "
                f"{getattr(item, 'title', '')}"
            )
        logger.debug("\n".join(lines))

    def _format_portfolio_context(self, symbol: str, portfolio: PortfolioState) -> str:
        """Format portfolio context for LLM."""
        lines = ["\n\n## Current Portfolio Context"]
        lines.append(f"Total Equity: ${portfolio.equity:,.2f}")
        lines.append(f"Cash Available: ${portfolio.cash:,.2f}")
        lines.append(f"Open Positions: {portfolio.position_count}")

        if symbol in portfolio.positions:
            pos = portfolio.positions[symbol]
            lines.append(f"\nCurrent {symbol} Position:")
            lines.append(f"  Shares: {pos.qty}")
            lines.append(f"  Avg Entry: ${pos.avg_entry_price:.2f}")
            lines.append(f"  Unrealized P&L: ${pos.unrealized_pnl:,.2f}")
        else:
            lines.append(f"\nNo current position in {symbol}")

        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> dict[str, Any]:
        """Parse LLM JSON response with error handling.

        Args:
            response: Raw response text from LLM.

        Returns:
            Parsed dictionary with signal, confidence, and metadata.
        """
        # Try to extract JSON from response
        try:
            # First, try direct JSON parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown code fence
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        json_match = re.search(r"\{[^{}]*\"signal\"[^{}]*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Last resort: try to extract signal keyword
        response_upper = response.upper()
        if "BUY" in response_upper and "SELL" not in response_upper:
            signal = "BUY"
        elif "SELL" in response_upper and "BUY" not in response_upper:
            signal = "SELL"
        else:
            signal = "HOLD"

        logger.warning(f"Could not parse LLM JSON, extracted signal: {signal}")
        return {
            "signal": signal,
            "confidence": 0.3,  # Low confidence for fallback parsing
            "reasoning": "Fallback parsing - original response was not valid JSON",
        }

    def reload_prompt(self) -> None:
        """Reload prompt from file/manager (useful after auto-improvement)."""
        self._system_prompt = None
        logger.info("Prompt reloaded")
