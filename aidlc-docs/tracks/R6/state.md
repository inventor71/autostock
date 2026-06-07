# Track R6 — ET (market timezone) helper consolidation

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R6
- **Title**: Consolidate market-timezone (ET) constant + `et_now()`/`et_today()` into `core`
- **Type**: refactor
- **Status**: merge-awaiting  <!-- Build & Test green (1033 passed) + /code-review fixes applied; committed on refactor/R6. Post-merge guide skipped: pure internal behavior-preserving refactor. -->
- **Branch**: refactor/R6
- **Worktree**: .claude/worktrees/R6
- **Submodule branch**: — (Python only)
- **Base commit**: 5e5c2a9 (main HEAD at resume; post R3/R4/R5)
- **Start Date**: 2026-06-07

## Extension Configuration
- **Security Baseline**: N/A.
- **Property-Based Testing**: N/A (a couple of unit tests suffice).

## Scope
The market timezone is re-declared in ~6 places under **two different (but equivalent) spellings**:
`ZoneInfo("US/Eastern")` and `ZoneInfo("America/New_York")`. `today_et()` lives in
`src/agent/steering/state.py` (a high-level module) yet is imported downward by
`src/agent/intraday/watch_store.py`; `src/agent/turn_log.py` has its own `compute_et_date()`.
Consolidate one `ET` constant + `et_now()`/`et_today()` in `src/core/` (depends on nothing — correct
layer) and migrate. **Pure T1** — `US/Eastern` and `America/New_York` are tz-db aliases (identical
offset/DST), so normalization is behavior-preserving. See `inception/refactor/et-time-helpers/guide.md`.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/steering/{state,runtime}.py`, `src/agent/turn_log.py`,
  `src/core/trades.py`, `src/early_session/monitor.py`. `runtime.py`/`state.py` are hot.
- **API/시그니처 변경**: `today_et()` may move from `steering/state` to `core`; keep a re-export
  shim at the old path (or update importers) so nothing breaks — decide in Stage 3.

## Stage Progress (skill: ai-dlc-refactor)
- [x] Stage 1 — Baseline + characterization (`1-baseline.md`; `tests/test_markettime.py` proves
      `US/Eastern`≡`America/New_York` across DST → T1 gate cleared)
- [x] Stage 2 — Tier ledger (`2-tier-ledger.md`) — all-T1, no T3 gate
- [x] Stage 3 — Redesign (`3-redesign.md`) — `core/markettime.py` (ET/et_now/et_today); rename
      `today_et`→`et_today` (no shim, removes downward-import smell); `compute_et_date` kept,
      constant-swapped; scheduler/KST left separate
- [x] Stage 4 — Implementation — new `src/core/markettime.py`; 6 constant dups → shared `ET`;
      `today_et`→`et_today` migrated (state/channel/watch_store + 2 test monkeypatch targets);
      `turn_log`/`runtime`/`trades` use shared `ET`
- [x] Build & Test — full suite **1033 passed, 0 failed**; py_compile clean
- [x] /code-review (high) fixes — folded in 7th ET dup `scripts/agent_trace.py` (sys.path + core
      import, mirrors status/health scripts; verified `python scripts/agent_trace.py --help` resolves);
      de-flaked `test_et_today_is_current_et_date` (bracket the ET-midnight rollover). Suite still 1033.
