"""File-based journal: the agent's durable memory across daily sessions.

The journal lives under ``workspace/`` (gitignored runtime state) and is the
single source of truth that survives the daily session restart. Human-readable
narrative is markdown (regime, watchlist, per-symbol theses, lessons, daily
notes); machine-executable actions are append-only JSON lines in
``decisions.jsonl`` -- the input the deterministic execution layer consumes.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field, field_validator

# repo root: src/agent/journal.py -> parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / "workspace"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

DecisionAction = Literal["BUY", "SELL", "HOLD", "ADJUST_STOP"]

LESSON_CATEGORIES = (
    "entry_timing", "exit_timing", "risk_mgmt", "regime",
    "thesis", "sizing", "other",
)


class LessonRecord(BaseModel):
    lesson_id: str
    date: str = Field(default_factory=lambda: date.today().isoformat())
    category: str = "other"
    signal_used: str = ""
    outcome: str = ""
    takeaway: str = ""
    times_applied: int = 0


class Decision(BaseModel):
    """One machine-executable action line in ``decisions.jsonl``.

    The agent proposes; deterministic Python (RiskManager -> Broker) executes.
    ``limit``/``stop``/``target`` are the LLM-suggested levels that become a
    resting bracket order (see RiskManager); ``valid_until`` lets a stale
    decision be ignored by the executor.
    """

    ts: datetime = Field(default_factory=datetime.now)
    symbol: str
    action: DecisionAction
    turn_id: str | None = None
    # F4: who originated this decision. Existing lines without the field parse as
    # "agent" (backward compatible). Human-forced trades from the steering console
    # are tagged "human" so they're distinguishable in journal/logs and drive the
    # human-lock state machine.
    source: Literal["agent", "human"] = "agent"
    # confidence/sell_pct are nullable: LLM output routinely sends null (e.g.
    # sell_pct on a BUY). Range is clamped downstream by the executor, not here,
    # so a stray value never blocks parsing a real decision line.
    confidence: float | None = 0.5
    sell_pct: float | None = 1.0
    limit: float | None = None  # suggested entry (None = market)
    stop: float | None = None  # suggested stop-loss level
    target: float | None = None  # suggested take-profit level
    thesis_ref: str | None = None  # e.g. "positions/AAPL.md"
    valid_until: datetime | None = None
    reason: str = ""

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return v.upper()


class Journal:
    """Read/write access to the agent's workspace files."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else DEFAULT_ROOT
        self.positions_dir = self.root / "positions"
        self.daily_dir = self.root / "daily"
        self.decisions_file = self.root / "decisions.jsonl"
        self.regime_file = self.root / "regime.md"
        self.watchlist_file = self.root / "watchlist.md"
        self.lessons_file = self.root / "lessons.md"
        self.claude_md = self.root / "CLAUDE.md"

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    def init(self) -> None:
        """Create the workspace tree and seed files if missing (idempotent)."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.positions_dir.mkdir(exist_ok=True)
        self.daily_dir.mkdir(exist_ok=True)

        if not self.claude_md.exists():
            template = TEMPLATE_DIR / "CLAUDE.md"
            if template.exists():
                self.claude_md.write_text(template.read_text())

        for path, header in (
            (self.regime_file, "# Market Regime\n\n_No regime note yet._\n"),
            (self.watchlist_file, "# Watchlist\n\n_Empty._\n"),
            (self.lessons_file, "# Lessons\n\n_No lessons recorded yet._\n"),
        ):
            if not path.exists():
                path.write_text(header)

    # ------------------------------------------------------------------ #
    # decisions.jsonl (machine-readable action log)
    # ------------------------------------------------------------------ #
    def append_decision(self, decision: Decision) -> None:
        """Append one decision as a JSON line (creates the file if needed)."""
        self.root.mkdir(parents=True, exist_ok=True)
        with self.decisions_file.open("a", encoding="utf-8") as fh:
            fh.write(decision.model_dump_json() + "\n")

    def read_decisions(
        self,
        symbol: str | None = None,
        since: datetime | None = None,
    ) -> list[Decision]:
        """Read decisions, optionally filtered by symbol and/or earliest ts."""
        if not self.decisions_file.exists():
            return []
        # Torn-safe shared reader (C-5/BR-11): the agent subprocess appends to
        # this file cross-process, so only consume complete (newline-terminated)
        # lines -- a half-written trailing line is left for the next read.
        from src.agent.steering.jsonl import read_complete_lines

        out: list[Decision] = []
        lines, _ = read_complete_lines(self.decisions_file, 0)
        for line in lines:
            try:
                decision = Decision.model_validate_json(line)
            except Exception as exc:  # one malformed LLM-written line must not sink the read
                logger.warning(f"Skipping unparseable decision line: {exc}")
                continue
            if symbol is not None and decision.symbol != symbol.upper():
                continue
            if since is not None and decision.ts < since:
                continue
            out.append(decision)
        return out

    # ------------------------------------------------------------------ #
    # Per-symbol thesis files
    # ------------------------------------------------------------------ #
    def position_file(self, symbol: str) -> Path:
        return self.positions_dir / f"{symbol.upper()}.md"

    def read_position(self, symbol: str) -> str | None:
        path = self.position_file(symbol)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_position(self, symbol: str, content: str) -> None:
        self.positions_dir.mkdir(parents=True, exist_ok=True)
        self.position_file(symbol).write_text(content, encoding="utf-8")

    def list_positions(self) -> list[str]:
        """Symbols that have a thesis file, sorted."""
        if not self.positions_dir.exists():
            return []
        return sorted(p.stem for p in self.positions_dir.glob("*.md"))

    # ------------------------------------------------------------------ #
    # Daily notes
    # ------------------------------------------------------------------ #
    def daily_file(self, day: date | None = None) -> Path:
        day = day or date.today()
        return self.daily_dir / f"{day.isoformat()}.md"

    def write_daily(self, content: str, day: date | None = None) -> None:
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.daily_file(day).write_text(content, encoding="utf-8")

    def read_daily(self, day: date | None = None) -> str | None:
        path = self.daily_file(day)
        return path.read_text(encoding="utf-8") if path.exists() else None

    # ------------------------------------------------------------------ #
    # Single-document sections (markdown)
    # ------------------------------------------------------------------ #
    def read_regime(self) -> str | None:
        return self.regime_file.read_text(encoding="utf-8") if self.regime_file.exists() else None

    def write_regime(self, content: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.regime_file.write_text(content, encoding="utf-8")

    def read_watchlist(self) -> str | None:
        return self.watchlist_file.read_text(encoding="utf-8") if self.watchlist_file.exists() else None

    def write_watchlist(self, content: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.watchlist_file.write_text(content, encoding="utf-8")

    def read_lessons(self) -> str | None:
        return self.lessons_file.read_text(encoding="utf-8") if self.lessons_file.exists() else None

    def append_lesson(self, text: str) -> None:
        """Append a dated lesson bullet to the curated lessons KB."""
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = date.today().isoformat()
        existing = self.read_lessons() or "# Lessons\n"
        if existing and not existing.endswith("\n"):
            existing += "\n"
        self.lessons_file.write_text(f"{existing}- [{stamp}] {text}\n", encoding="utf-8")

    # ------------------------------------------------------------------ #
    # Structured lessons (F23)
    # ------------------------------------------------------------------ #
    @property
    def lessons_jsonl(self) -> Path:
        return self.root / "lessons.jsonl"

    def read_lessons_jsonl(self) -> list[LessonRecord]:
        if not self.lessons_jsonl.exists():
            return []
        from src.agent.steering.jsonl import read_complete_lines

        out: list[LessonRecord] = []
        lines, _ = read_complete_lines(self.lessons_jsonl, 0)
        for line in lines:
            try:
                out.append(LessonRecord.model_validate_json(line))
            except Exception as exc:
                logger.warning(f"Skipping unparseable lesson line: {exc}")
        return out

    def next_lesson_id(self) -> str:
        existing = self.read_lessons_jsonl()
        if not existing:
            return "L001"
        nums = []
        for r in existing:
            try:
                nums.append(int(r.lesson_id.lstrip("L")))
            except ValueError:
                continue
        return f"L{max(nums, default=0) + 1:03d}"

    def append_lesson_record(self, record: LessonRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lessons_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        self.append_lesson(f"[{record.category}] {record.takeaway}")
