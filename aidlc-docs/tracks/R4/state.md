# Track R4 — JSONL record read/write helper (de-dup)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R4
- **Title**: Consolidate JSONL record read/write into `src/core/jsonl.py`
- **Type**: refactor
- **Status**: merged → main f43366f (2026-06-07)  <!-- Build & Test green (1028 passed) -->
- **Branch**: refactor/R4
- **Worktree**: .claude/worktrees/R4
- **Submodule branch**: — (Python only)
- **Base commit**: 9e9aec2 (main HEAD at pick-up)
- **Start Date**: 2026-06-06

## Extension Configuration
- **Security Baseline**: N/A (no new I/O surface, no secrets).
- **Property-Based Testing**: Recommended — round-trip PBT (`append_record` → `read_records` == input)
  mirrors `tests/signals/test_records_roundtrip.py`.

## Scope
~8 readers + ~7 writers re-implement the same "open file → iterate lines → `json.loads` →
`model_validate` → append" / "`f.write(model_dump_json()+\n)`" pattern. Extract a tiny
`src/core/jsonl.py` and migrate call sites. **Pure T1** (behavior-preserving). Mechanical but
touches many files lightly → coordinate timing with other tracks (merge-conflict surface).
See `inception/refactor/jsonl-helper/guide.md`.

## Merge Risk Notes
- **공유 파일 (주의)**: touches `src/agent/{equity_log,trades_log,turn_log,journal}.py`,
  `src/agent/steering/{runtime,channel,commands}.py`, `src/surge/store.py`,
  `src/early_session/{records,index_writer,__main__}.py`, `src/agent/intraday/watch_store.py`.
  Wide light touch → do this when those areas are quiet (no active F-track editing them).
- **API/시그니처 변경**: none public; internal helper introduction only.

## Stage Progress (skill: ai-dlc-refactor)
- [x] Stage 1 — Baseline (`1-baseline.md`) + characterization (`tests/test_jsonl.py`, 10 tests)
- [x] Stage 2 — Tier ledger (`2-tier-ledger.md`) — all-T1, no T3 gate
- [x] Stage 3 — Redesign (`3-redesign.md`) — `core/jsonl.py` API + shim + migration order
- [x] Stage 4 — Implementation (`4-implementation.md`) — promoted primitives + 3 helpers; migrated
      equity/trades/turn/surge; steering→shim
- [x] Build & Test — full suite **984 passed, 0 failed**; py_compile clean
- Status: **merged** → main f43366f (2026-06-07)
