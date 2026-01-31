"""Prompt version management for LLM trading strategy."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class BacktestMetrics(BaseModel):
    """Backtest performance metrics for a prompt version."""

    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    symbols: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""


class PromptVersion(BaseModel):
    """A versioned trading prompt with associated backtest results."""

    version: str
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
    description: str = ""
    backtest_results: list[BacktestMetrics] = Field(default_factory=list)
    parent_version: str | None = None
    improvement_notes: str = ""

    @property
    def best_sharpe(self) -> float:
        """Get best Sharpe ratio across all backtests."""
        if not self.backtest_results:
            return 0.0
        return max(r.sharpe_ratio for r in self.backtest_results)

    @property
    def avg_return(self) -> float:
        """Get average return across all backtests."""
        if not self.backtest_results:
            return 0.0
        return sum(r.total_return_pct for r in self.backtest_results) / len(self.backtest_results)

    def add_backtest_result(self, metrics: BacktestMetrics) -> None:
        """Add backtest result to this version."""
        self.backtest_results.append(metrics)


class PromptHistory(BaseModel):
    """History of all prompt versions."""

    versions: dict[str, PromptVersion] = Field(default_factory=dict)
    current_version: str = "v1"

    def add_version(self, version: PromptVersion) -> None:
        """Add a new prompt version."""
        self.versions[version.version] = version

    def get_version(self, version_id: str) -> PromptVersion | None:
        """Get a specific version."""
        return self.versions.get(version_id)

    def get_latest(self) -> PromptVersion | None:
        """Get the most recently created version."""
        if not self.versions:
            return None
        return max(self.versions.values(), key=lambda v: v.created_at)

    def get_best(self, metric: str = "sharpe_ratio") -> PromptVersion | None:
        """Get the version with best performance on specified metric."""
        if not self.versions:
            return None

        def score(v: PromptVersion) -> float:
            if not v.backtest_results:
                return float("-inf")
            if metric == "sharpe_ratio":
                return v.best_sharpe
            elif metric == "total_return_pct":
                return v.avg_return
            else:
                return max(getattr(r, metric, 0) for r in v.backtest_results)

        return max(self.versions.values(), key=score)

    def next_version_id(self) -> str:
        """Generate next version ID (v1, v2, v3, ...)."""
        if not self.versions:
            return "v1"
        max_num = max(
            int(v[1:]) for v in self.versions.keys() if v.startswith("v") and v[1:].isdigit()
        )
        return f"v{max_num + 1}"


class PromptManager:
    """Manages prompt versions and persistence."""

    def __init__(self, prompts_dir: Path | str | None = None):
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent.parent.parent / "config" / "prompts"
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.prompts_dir / "prompt_history.json"
        self._history: PromptHistory | None = None

    @property
    def history(self) -> PromptHistory:
        """Lazy load prompt history."""
        if self._history is None:
            self._history = self._load_history()
        return self._history

    def _load_history(self) -> PromptHistory:
        """Load prompt history from JSON file."""
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    data = json.load(f)
                return PromptHistory.model_validate(data)
            except Exception as e:
                logger.warning(f"Could not load prompt history: {e}")

        # Initialize with v1 prompt if exists
        history = PromptHistory()
        v1_file = self.prompts_dir / "trading_prompt_v1.txt"
        if v1_file.exists():
            content = v1_file.read_text()
            v1 = PromptVersion(
                version="v1",
                content=content,
                description="Initial trading prompt",
            )
            history.add_version(v1)

        return history

    def _save_history(self) -> None:
        """Save prompt history to JSON file."""
        with open(self.history_file, "w") as f:
            json.dump(self.history.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug(f"Saved prompt history to {self.history_file}")

    def get_prompt(self, version: str = "latest") -> PromptVersion | None:
        """Get a prompt by version identifier.

        Args:
            version: Version ID ("v1", "v2", ...) or special values:
                - "latest": Most recently created version
                - "best": Version with best backtest performance

        Returns:
            PromptVersion or None if not found.
        """
        if version == "latest":
            return self.history.get_latest()
        elif version == "best":
            return self.history.get_best()
        else:
            return self.history.get_version(version)

    def save_prompt(
        self,
        content: str,
        version: str | None = None,
        description: str = "",
        parent_version: str | None = None,
        improvement_notes: str = "",
    ) -> PromptVersion:
        """Save a new prompt version.

        Args:
            content: Prompt text content.
            version: Version ID (auto-generated if None).
            description: Optional description.
            parent_version: Parent version if this is an improvement.
            improvement_notes: Notes about what was improved.

        Returns:
            The created PromptVersion.
        """
        if version is None:
            version = self.history.next_version_id()

        prompt = PromptVersion(
            version=version,
            content=content,
            description=description,
            parent_version=parent_version,
            improvement_notes=improvement_notes,
        )
        self.history.add_version(prompt)
        self.history.current_version = version

        # Also save as text file for easy editing
        prompt_file = self.prompts_dir / f"trading_prompt_{version}.txt"
        prompt_file.write_text(content)

        self._save_history()
        logger.info(f"Saved prompt version {version}")
        return prompt

    def record_backtest_result(
        self,
        version: str,
        result: Any,
    ) -> None:
        """Record backtest results for a prompt version.

        Args:
            version: Version ID to update.
            result: BacktestResult object with performance metrics.
        """
        prompt = self.history.get_version(version)
        if prompt is None:
            logger.warning(f"Cannot record results: version {version} not found")
            return

        metrics = BacktestMetrics(
            total_return_pct=result.total_return_pct,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            win_rate=result.win_rate,
            profit_factor=result.profit_factor,
            total_trades=result.total_trades,
            start_date=str(result.start_date),
            end_date=str(result.end_date),
        )
        prompt.add_backtest_result(metrics)
        self._save_history()
        logger.info(
            f"Recorded backtest for {version}: "
            f"return={metrics.total_return_pct:.2f}%, sharpe={metrics.sharpe_ratio:.2f}"
        )

    def list_versions(self) -> list[dict[str, Any]]:
        """List all versions with summary info."""
        result = []
        for v in self.history.versions.values():
            result.append({
                "version": v.version,
                "created_at": v.created_at.isoformat(),
                "description": v.description,
                "backtest_count": len(v.backtest_results),
                "best_sharpe": v.best_sharpe,
                "avg_return": v.avg_return,
            })
        return sorted(result, key=lambda x: x["version"])

    def compare_versions(self, v1: str, v2: str) -> dict[str, Any]:
        """Compare two prompt versions by their backtest results."""
        p1 = self.history.get_version(v1)
        p2 = self.history.get_version(v2)

        if p1 is None or p2 is None:
            return {"error": "One or both versions not found"}

        return {
            "v1": {
                "version": v1,
                "best_sharpe": p1.best_sharpe,
                "avg_return": p1.avg_return,
                "backtest_count": len(p1.backtest_results),
            },
            "v2": {
                "version": v2,
                "best_sharpe": p2.best_sharpe,
                "avg_return": p2.avg_return,
                "backtest_count": len(p2.backtest_results),
            },
            "sharpe_improvement": p2.best_sharpe - p1.best_sharpe,
            "return_improvement": p2.avg_return - p1.avg_return,
        }
