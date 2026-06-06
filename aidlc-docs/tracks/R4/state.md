# Track R4 — JSONL record read/write helper (de-dup)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R4
- **Title**: Consolidate JSONL record read/write into `src/core/jsonl.py`
- **Type**: refactor
- **Status**: backlog  <!-- not started; pick up via /ai-dlc-resume or /ai-dlc-refactor -->
- **Branch**: refactor/R4 (TBD)
- **Worktree**: .claude/worktrees/R4 (TBD)
- **Submodule branch**: — (Python only)
- **Base commit**: ec2875c (survey point; rebase when picked up)
- **Start Date**: TBD

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

## Stage Progress (skill: ai-dlc-refactor) — NOT STARTED
- [ ] Stage 1 — Baseline + characterization (lean on existing per-log round-trip tests)
- [ ] Stage 2 — Tier ledger (expect all-T1)
- [ ] Stage 3 — Redesign (`read_records`/`append_record` signature; corruption/empty-line policy)
- [ ] Stage 4 — Implementation (migrate call sites incrementally, green per file)
- [ ] Build & Test
