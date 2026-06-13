"""Fixture / record interception for the agent tool CLI (F74 eval harness).

The eval harness must control every market-data answer the agent sees, and a
turn must never silently fall back to live data. Faking the upstream objects
(yfinance ``Ticker``, brokers) per tool is fragile; instead the dispatch in
``__main__.main`` is intercepted ONCE, before any data wiring runs, and serves
the **final tool output JSON** from a scenario fixture. The fixture contract is
therefore exactly what the agent observes — authorable by hand or captured from
a real session via record mode.

Activation is by environment variable so the interception crosses the process
boundary (the agent calls tools as a subprocess):

- ``AUTOSTOCK_TOOLS_FIXTURE_DIR``: serve market commands from this directory.
- ``AUTOSTOCK_TOOLS_RECORD_DIR``: after a real run, persist the output here.

Workspace commands (lesson/watch/surge-*) are never intercepted — they operate
on the (sandbox) journal root and must keep working inside an eval turn.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

FIXTURE_ENV = "AUTOSTOCK_TOOLS_FIXTURE_DIR"
RECORD_ENV = "AUTOSTOCK_TOOLS_RECORD_DIR"

#: Key used for commands that take no symbol (account/macro/scoreboard/...).
NO_SYMBOL_KEY = "_"

#: Market-data commands: in fixture mode these are answered from the fixture
#: and the real data wiring is never touched. Everything else (lesson, watch,
#: surge-list, surge-analyze) passes through to the sandbox workspace.
MARKET_COMMANDS = frozenset({
    "quote", "indicators", "fundamentals", "news", "scoreboard",
    "earnings", "insider", "analyst_upgrades", "institutional", "short_data",
    "macro", "account", "movers", "readthrough", "earnings_calendar",
    "ipo_calendar",
})


def command_key(args) -> str:
    """The fixture key for a parsed argparse namespace: symbol or "_"."""
    sym = getattr(args, "symbol", None)
    return sym.upper() if sym else NO_SYMBOL_KEY


class FixtureStore:
    """Read-only view over a fixture directory (one JSON file per command)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @classmethod
    def from_env(cls) -> "FixtureStore | None":
        path = os.environ.get(FIXTURE_ENV)
        return cls(path) if path else None

    def _file(self, cmd: str) -> Path:
        return self.root / f"{cmd}.json"

    def get(self, cmd: str, key: str) -> dict | list:
        """The stored output for (cmd, key), or an explicit fixture_missing
        error object — never a silent fallback to live data."""
        missing = {
            "error": "fixture_missing",
            "tool": cmd,
            "key": key,
            "fixture_dir": str(self.root),
        }
        f = self._file(cmd)
        if not f.exists():
            return missing
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {**missing, "error": "fixture_unreadable"}
        if not isinstance(data, dict) or key not in data:
            return missing
        return data[key]


class RecordingStore:
    """Persist real tool outputs into the fixture format (scenario capture)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @classmethod
    def from_env(cls) -> "RecordingStore | None":
        path = os.environ.get(RECORD_ENV)
        return cls(path) if path else None

    def save(self, cmd: str, key: str, output) -> None:
        """Merge ``output`` under (cmd, key). Atomic replace; concurrent tool
        subprocesses may interleave whole-file merges (last writer wins per
        file) — acceptable for a capture aid, not a database."""
        self.root.mkdir(parents=True, exist_ok=True)
        f = self.root / f"{cmd}.json"
        data: dict = {}
        if f.exists():
            try:
                existing = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    data = existing
            except (OSError, json.JSONDecodeError):
                pass  # unreadable capture file: start fresh rather than abort the tool
        data[key] = output
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, f)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
