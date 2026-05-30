# Build Instructions — Unit `intraday-redesign` (F3)

> Pure-Python unit (no compile step). "Build" = resolve deps + import-smoke.
> Branch `feat/intraday-redesign` (worktree `.claude/worktrees/intraday-redesign`, off `main`). **0 new runtime dependencies.**

## Prerequisites
- **Runtime**: Python 3.11+ (verified 3.12). Build system: Hatchling / `pyproject.toml`.
- **Dependencies**: existing only — `pydantic`, `loguru`, `apscheduler`, `alpaca-py` (0.43.2), `yfinance`, `pandas`; dev: `pytest`, `hypothesis`. No additions.
- **Env vars** (only for the optional live check, not for build/tests): `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` in the **main repo** `.env` (gitignored; NOT present in the worktree — see live-verification note below).
- **System**: local CLI/daemon, no cloud infra, no DB.

## Build Steps

### 1. Install dependencies (already satisfied in the project venv)
```bash
# from the repo root, using the shared venv
/home/jihoonpark/Project/autostock/venv/bin/python -m pip install -e .   # or: pip install -r requirements
/home/jihoonpark/Project/autostock/venv/bin/python -m pip check          # -> "No broken requirements found."
```

### 2. Configure environment
No build-time env needed. (Runtime: the daemon runs `python main.py --mode agent --steering`; F3 is inactive without `--steering` and falls back to the legacy intraday prompt — NFR-8.)

### 3. "Build" all units (import-smoke — no compilation)
```bash
cd /home/jihoonpark/Project/autostock/.claude/worktrees/intraday-redesign
/home/jihoonpark/Project/autostock/venv/bin/python -c "import src, main; \
from src.agent.intraday import records, watch_store, bars, abnormal, brief, news_diff, wake, settings; \
from src.trading.modes.agent import AgentTradingMode; print('package import OK')"
```

### 4. Verify build success
- **Expected output**: `package import OK` and `No broken requirements found.`
- **Artifacts**: none (no wheel/binary required for the daemon run). New source modules under `src/agent/intraday/`.
- **Acceptable warnings**: `PytestConfigWarning: Unknown config option: asyncio_mode` and `websockets.legacy ... DeprecationWarning` — pre-existing, unrelated to F3.

## Troubleshooting
- **ImportError `src.agent.intraday...`** → run from the worktree root (the F3 code is only on `feat/intraday-redesign`, not on `main`).
- **`pip check` reports a conflict** → not introduced by F3 (0 new deps); re-sync the venv against the project's pinned deps.
- **Live broker call returns empty keys from the worktree** → `.env` is not in the worktree; inject the main repo `.env` via `dotenv` (see `build-and-test-summary.md` §Live verification and project memory `worktree-live-verification`).
