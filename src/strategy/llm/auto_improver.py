"""Automatic prompt improvement based on backtest results."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.models import BacktestResult, FilledOrder
from src.strategy.llm.client import BaseLLMClient, create_llm_client
from src.strategy.llm.prompt_manager import PromptManager, PromptVersion


class PromptAutoImprover:
    """Analyzes backtest results and generates improved prompts.

    Uses an LLM to analyze trading performance and suggest
    prompt improvements based on patterns in the results.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient | None = None,
        prompt_manager: PromptManager | None = None,
        improvement_prompt_path: Path | str | None = None,
        provider: str = "claude",
        api_key: str = "",
    ):
        self._client = llm_client
        # Provider/key are injected by the composition root; used only to build
        # the client lazily when one wasn't supplied directly.
        self._provider = provider
        self._api_key = api_key
        self._prompt_manager = prompt_manager or PromptManager()

        if improvement_prompt_path is None:
            improvement_prompt_path = (
                Path(__file__).parent.parent.parent.parent
                / "config"
                / "prompts"
                / "improvement_prompt.txt"
            )
        self.improvement_prompt_path = Path(improvement_prompt_path)

    @property
    def client(self) -> BaseLLMClient:
        """Get or initialize LLM client (provider/api_key injected by caller)."""
        if self._client is None:
            self._client = create_llm_client(
                provider=self._provider,
                api_key=self._api_key,
                temperature=0.7,  # Slightly higher for creative improvements
            )
        return self._client

    def analyze_and_improve(
        self,
        current_version: str,
        backtest_results: list[BacktestResult],
    ) -> PromptVersion | None:
        """Analyze backtest results and generate improved prompt.

        Args:
            current_version: Version ID of current prompt.
            backtest_results: List of backtest results to analyze.

        Returns:
            New PromptVersion with improved prompt, or None on failure.
        """
        if not backtest_results:
            logger.warning("No backtest results to analyze")
            return None

        # Get current prompt
        current_prompt = self._prompt_manager.get_prompt(current_version)
        if current_prompt is None:
            logger.error(f"Prompt version {current_version} not found")
            return None

        # Format analysis context
        context = self._format_analysis_context(backtest_results, current_prompt)

        # Load improvement system prompt
        system_prompt = self._load_improvement_prompt()

        # Call LLM for analysis and improvement
        try:
            response = self.client.complete(
                system_prompt=system_prompt,
                user_message=context,
                max_tokens=4096,
            )

            improvement_data = self._parse_improvement_response(response)
            if improvement_data is None:
                logger.error("Failed to parse improvement response")
                return None

            # Create new version
            new_prompt = self._prompt_manager.save_prompt(
                content=improvement_data["improved_prompt"],
                description=f"Auto-improved from {current_version}",
                parent_version=current_version,
                improvement_notes=self._format_improvement_notes(improvement_data),
            )

            logger.info(
                f"Created improved prompt {new_prompt.version} from {current_version}"
            )
            return new_prompt

        except Exception as e:
            logger.error(f"Error during prompt improvement: {e}")
            return None

    def _format_analysis_context(
        self,
        results: list[BacktestResult],
        current_prompt: PromptVersion,
    ) -> str:
        """Format backtest results for LLM analysis."""
        lines = ["## Current Trading Prompt", "```", current_prompt.content, "```", ""]

        lines.append("## Backtest Results Summary")

        # Aggregate metrics
        total_return = sum(r.total_return_pct for r in results) / len(results)
        avg_sharpe = sum(r.sharpe_ratio for r in results) / len(results)
        avg_drawdown = sum(r.max_drawdown_pct for r in results) / len(results)
        avg_win_rate = sum(r.win_rate for r in results) / len(results)
        total_trades = sum(r.total_trades for r in results)

        lines.append(f"- Number of Symbols Tested: {len(results)}")
        lines.append(f"- Average Total Return: {total_return:.2f}%")
        lines.append(f"- Average Sharpe Ratio: {avg_sharpe:.2f}")
        lines.append(f"- Average Max Drawdown: {avg_drawdown:.2f}%")
        lines.append(f"- Average Win Rate: {avg_win_rate:.1%}")
        lines.append(f"- Total Trades: {total_trades}")
        lines.append("")

        # Per-symbol breakdown
        lines.append("## Per-Symbol Performance")
        for r in results:
            symbol = getattr(r, "symbol", "N/A")
            lines.append(f"\n### {r.strategy_name} - {symbol}")
            lines.append(f"- Return: {r.total_return_pct:.2f}%")
            lines.append(f"- Sharpe: {r.sharpe_ratio:.2f}")
            lines.append(f"- Drawdown: {r.max_drawdown_pct:.2f}%")
            lines.append(f"- Win Rate: {r.win_rate:.1%}")
            lines.append(f"- Trades: {r.total_trades}")

        # Trade analysis
        all_trades = []
        for r in results:
            if hasattr(r, "trades") and r.trades:
                all_trades.extend(r.trades)

        if all_trades:
            lines.append("")
            lines.append("## Trade Analysis")
            lines.append(self._analyze_trades(all_trades))

        # Identify issues
        lines.append("")
        lines.append("## Potential Issues")
        lines.extend(self._identify_issues(results))

        return "\n".join(lines)

    def _analyze_trades(self, trades: list[FilledOrder]) -> str:
        """Analyze trade patterns."""
        if not trades:
            return "No trade data available."

        lines = []

        # Separate buys and sells
        buys = [t for t in trades if t.side.value == "buy"]
        sells = [t for t in trades if t.side.value == "sell"]

        lines.append(f"- Total Buy Orders: {len(buys)}")
        lines.append(f"- Total Sell Orders: {len(sells)}")

        # Time distribution
        if buys:
            buy_times = [t.filled_at.hour for t in buys if t.filled_at]
            if buy_times:
                lines.append(f"- Most Active Buy Hour: {max(set(buy_times), key=buy_times.count)}")

        return "\n".join(lines)

    def _identify_issues(self, results: list[BacktestResult]) -> list[str]:
        """Identify potential issues from backtest results."""
        issues = []

        avg_return = sum(r.total_return_pct for r in results) / len(results)
        avg_sharpe = sum(r.sharpe_ratio for r in results) / len(results)
        avg_win_rate = sum(r.win_rate for r in results) / len(results)
        avg_drawdown = sum(r.max_drawdown_pct for r in results) / len(results)

        if avg_return < 0:
            issues.append("- NEGATIVE RETURNS: Strategy is losing money on average")

        if avg_sharpe < 0.5:
            issues.append("- LOW SHARPE RATIO: Poor risk-adjusted returns")

        if avg_win_rate < 0.4:
            issues.append("- LOW WIN RATE: Too many losing trades")
        elif avg_win_rate > 0.8:
            issues.append("- VERY HIGH WIN RATE: May be cutting winners too early")

        if avg_drawdown > 25:
            issues.append("- HIGH DRAWDOWN: Significant capital at risk")

        total_trades = sum(r.total_trades for r in results)
        days = sum(
            (r.end_date - r.start_date).days for r in results
        ) / len(results) if results else 1
        trades_per_day = total_trades / (days * len(results)) if days > 0 else 0

        if trades_per_day < 0.05:
            issues.append("- LOW TRADING FREQUENCY: May be missing opportunities")
        elif trades_per_day > 2:
            issues.append("- HIGH TRADING FREQUENCY: Possible overtrading")

        # Check for underperformers
        losers = [r for r in results if r.total_return_pct < -5]
        if len(losers) > len(results) // 2:
            issues.append(f"- MANY LOSING SYMBOLS: {len(losers)}/{len(results)} symbols lost >5%")

        if not issues:
            issues.append("- No major issues identified")

        return issues

    def _load_improvement_prompt(self) -> str:
        """Load the improvement system prompt."""
        if self.improvement_prompt_path.exists():
            return self.improvement_prompt_path.read_text()

        # Fallback minimal prompt
        return """Analyze the trading backtest results and improve the prompt.
Respond with JSON containing: analysis, improvements, improved_prompt."""

    def _parse_improvement_response(self, response: str) -> dict[str, Any] | None:
        """Parse the LLM improvement response."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from code block
        json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object
        json_match = re.search(r"\{[\s\S]*\"improved_prompt\"[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.error("Could not parse improvement response as JSON")
        return None

    def _format_improvement_notes(self, improvement_data: dict) -> str:
        """Format improvement notes from analysis."""
        notes = []

        if "analysis" in improvement_data:
            analysis = improvement_data["analysis"]
            if "weaknesses" in analysis:
                notes.append("Weaknesses addressed:")
                for w in analysis["weaknesses"][:3]:
                    notes.append(f"  - {w}")

        if "improvements" in improvement_data:
            notes.append("\nChanges made:")
            for imp in improvement_data["improvements"][:5]:
                notes.append(f"  - [{imp.get('area', 'general')}] {imp.get('change', '')}")

        return "\n".join(notes)


def run_improvement_cycle(
    backtest_results: list[BacktestResult],
    current_version: str = "latest",
    iterations: int = 1,
) -> list[PromptVersion]:
    """Run one or more improvement cycles.

    Args:
        backtest_results: Initial backtest results to analyze.
        current_version: Starting prompt version.
        iterations: Number of improvement iterations.

    Returns:
        List of new prompt versions created.
    """
    improver = PromptAutoImprover()
    new_versions = []

    version = current_version
    for i in range(iterations):
        logger.info(f"Starting improvement iteration {i + 1}/{iterations}")

        new_version = improver.analyze_and_improve(version, backtest_results)
        if new_version is None:
            logger.warning(f"Improvement iteration {i + 1} failed")
            break

        new_versions.append(new_version)
        version = new_version.version

        # Note: In a real scenario, you would re-run backtest here
        # and use those results for the next iteration
        logger.info(f"Created {new_version.version}")

    return new_versions
