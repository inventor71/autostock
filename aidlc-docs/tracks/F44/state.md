# Track F44 — 진행 중 turn 라벨 + 동일 type turn dedup

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F44
- **Title**: 진행 중 turn 라벨(TUI) + 동일 type turn이 in-flight면 큐잉 대신 "already in progress" 반환
- **Type**: feature
- **Status**: merge-awaiting  <!-- Build & Test green (pytest 647 / tui-trading 52 / typecheck 19) -->
- **Branch**: feat/F44
- **Worktree**: .claude/worktrees/F44
- **Submodule branch**: — (monorepo, post-F35; operator-console/cli touched for the label)
- **Base commit**: bc25f93
- **Start Date**: 2026-06-03T12:05:32Z

## Extension Configuration
- **Security Baseline**: Disabled — 신규 외부 표면/시크릿 없음(라벨=turn type/시간만). 대부분 규칙 N/A.
- **Property-Based Testing**: Enabled — Unit1 dedup 동시성/상태전이 불변식(hypothesis).

## Scope
두 가지 (서로 독립):
1. **진행 라벨 (TUI)** — research/intraday/eod 등 turn이 in-flight인 동안 "지금 무슨 turn이
   몇 분째 돌고 있는지"를 화면에 텍스트로 노출. 현재는 now-cursor(▼/┃)가 초록 점멸하는
   신호뿐(`timeline-bar.tsx:174,238`)이라 관찰성이 약함. 데이터는 이미 monitor.json
   `current_turn = {id, type, started_at}`에 존재 — 재사용.
2. **동일 type turn dedup (daemon)** — 같은 type의 turn이 이미 진행 중이면 수동 트리거를
   큐에 넣지 않고 "이미 진행 중"을 반환. 현재 `_v_research`→`start_priority_async`는
   무조건 큐잉(dedup 없음)이라 `/research`를 두 번 누르면 둘 다 큐잉됨(이번 세션에서 관찰).

관련: [[steering-console-redesign]] [[f4-steering-runtime-wiring]] (F38 manual turn,
F41 current_turn/overlay).

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (`inception/requirements.md`)
- [x] User Stories — skip (운영자 1인, 변화 작음)
- [x] Workflow Planning — `inception/plan.md`
- [x] Application Design — skip (기존 컴포넌트 경계 내)
- [x] Units Generation — 2 units (daemon dedup / TUI label)
- [x] Construction (per-unit Code Generation)
  - [x] Unit1 turn-dedup (daemon, Python) — turns.py dedup + runtime trigger/publish + commands outcomes; tests green
  - [x] Unit2 progress-label (TUI, tui-trading) — StatusRow + fmtElapsedClock/fmtTurnLabel + queued plumbing; tests green
- [x] Build & Test — pytest 647 passed · tui-trading 52 pass · turbo typecheck 19/19

## Verification
- daemon: `venv/bin/python -m pytest -q` → **647 passed** (신규 `tests/test_turn_dedup_f44.py` 8개
  + `tests/test_steering_commands.py` already_running/already_queued 2개 포함; property-based 불변식 통과).
- TUI: `bun test` (tui-trading) → **52 pass** (신규 `test/progress-label.test.ts` 8개 포함).
- typecheck: `bun run typecheck` (turbo/tsgo) → **19/19 successful**.

## Extension 준수 요약
- **Property-Based Testing (Enabled)**: ✅ `test_property_no_duplicate_pending_per_type`
  (hypothesis, max_examples=60) — 무작위 트리거 시퀀스에서 type별 pending 중복 0 / 정상 배수.
- **Security Baseline (Disabled)**: 신규 외부 표면/시크릿 없음 → 규칙 대부분 N/A(라벨=turn type/시간만,
  monitor.json 파일 읽기만, 브로커/네트워크 접근 없음).

## 머지 노트 (concurrent)
- 트랙 문서·코드·테스트는 feat/F44에 커밋. 루트 레지스트리 행(F44)은 main 작업트리에서
  F45/F46 행과 함께 미커밋 상태로 공존 — `/ai-dlc-merge`가 머지시 main→merged로 플립.
- 이 트랙은 `timeline-bar.tsx` / `use-monitor-data.ts`를 건드림. **F45(타임라인 12h 윈도우),
  F32/F36(타임라인)** 와 같은 파일 영역 충돌 가능 → 머지 순서/리베이스 시 타임라인 변경 재확인 필요
  ([[feedback-refactor-merge-resweep]] 취지).
