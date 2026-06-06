# Track R6 — ET (market timezone) helper consolidation

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R6
- **Title**: Consolidate market-timezone (ET) constant + `et_now()`/`et_today()` into `core`
- **Type**: refactor
- **Status**: backlog  <!-- not started -->
- **Branch**: refactor/R6 (TBD)
- **Worktree**: .claude/worktrees/R6 (TBD)
- **Submodule branch**: — (Python only)
- **Base commit**: ec2875c (survey point; rebase when picked up)
- **Start Date**: TBD

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

## Stage Progress (skill: ai-dlc-refactor) — NOT STARTED
- [ ] Stage 1 — Baseline + characterization (existing tz behavior; alias equivalence check)
- [ ] Stage 2 — Tier ledger (expect all-T1)
- [ ] Stage 3 — Redesign (where it lives; re-export shim vs update-importers; KST left separate)
- [ ] Stage 4 — Implementation
- [ ] Build & Test
