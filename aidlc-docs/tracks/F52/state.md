# Track F52 — Research Turn SELL 결정 미실행 근본 원인 분석 (Broker Tool Unavailable)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F52
- **Title**: Research Turn SELL 결정 미실행 근본 원인 분석 (Broker Tool Unavailable / Lesson #11)
- **Type**: bug investigation (root-cause analysis)
- **Status**: merged → main 4e64781 (2026-06-04)
- **Branch**: feat/F52
- **Worktree**: .claude/worktrees/F52
- **Submodule branch**: —
- **Base commit**: a8957ad
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Disabled (bug fix within existing component boundaries; no new attack surface)
- **Property-Based Testing**: Disabled (executor tests use hand-written stubs; existing PBT for related components unchanged)

## Scope
Agent가 TSLA 7주에 대해 research turn에서 SELL 결정을 반복적으로 내렸으나, broker tool이 "lesson #11"로 인해 unavailable 상태여서 실제 sell order가 한 번도 실행되지 않은 근본 원인을 분석하고 수정한다.

**근본 원인**:
1. `execute_pending()`이 outcome과 무관하게 cursor를 unconditionally advance → 실패한 decision이 영구히 abandon됨
2. "no_order"/"error" outcome이 persistent audit trail 없이 Python logger에만 기록됨
3. 호출자가 return value를 discard하여 실패를 감지할 방법이 없었음

**수정 내용**:
- `_load_cursor`/`_save_cursor`: `terminal_indices` set 추가 → 해결된 decision만 cursor가 advance
- `_log_outcome`: 모든 outcome을 `execution_outcomes.jsonl`에 persistent 기록
- `_emit_exec_outcomes`: steering 활성화 시 실패 outcome을 channel event로 발행
- `_exec_pending_and_exits`: outcomes 반환하도록 변경

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/steering/records.py` — EventKind Literal에 "exec_outcome" 추가 (다른 트랙과 충돌 가능성 낮음)
- **API/시그니처 변경**: `_load_cursor()` → `tuple[int, set[int]]` 반환, `_save_cursor(n)` → `_save_cursor(cursor, terminal_indices)` — private 메서드, executor.py 내부에서만 호출
- **알려진 동시 변경**: 없음 (F51은 별도 영역)

## Stage Progress
- [x] Workspace Detection — Brownfield, track F52 created
- [x] Requirements Analysis — minimal (bug investigation)
- [x] Workflow Planning — direct investigation → plan approved
- [x] Root Cause Analysis — COMPLETE 2026-06-03
- [x] Code Generation — executor.py, agent.py, records.py 수정
- [x] Build & Test — 686 tests passed, 0 regressions
- [x] Track marked merge-awaiting
