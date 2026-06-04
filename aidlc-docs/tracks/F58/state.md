# Track F58 — 과거 날짜/타임라인 구간 상단바에 턴 토큰사용량 표시

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F58
- **Title**: 과거 날짜/타임라인 구간으로 이동 시 상단바에 턴들의 토큰사용량(또는 비용) 표시
- **Type**: feature
- **Status**: merged → main 0e071e1 (2026-06-04)
- **Branch HEAD**: f27c0e5 → rebased 4f9a79f → merge 0e071e1
- **Branch**: feat/F58
- **Worktree**: .claude/worktrees/F58
- **Submodule branch**: — (monorepo)
- **Base commit**: 03de978
- **Start Date**: 2026-06-04T00:38:59Z

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-03(no secrets in logs) 등 대부분 N/A 예상
  (UI 표시 + 저널 읽기). 확정은 요구사항 확정 후.
- **Property-Based Testing**: Enabled — 집계 합산 함수(순수)가 생기면 Partial 적용 검토.

## Scope (확정 전 — 요구사항 질문 진행 중)
NavRow(`operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx`)는
`· $cost` 를 `isLive()` 일 때만 표시(`today_cost_usd`). 과거 윈도우로 이동하면 아무것도
안 보임.

데이터 가용성:
- 과거: `turns.jsonl` 각 행에 `cost_usd` + `input_tokens` + `output_tokens` 존재
  (`src/agent/turn_log.py:163-167`). TUI `MonitorTurn` 타입은 토큰 필드를 누락.
- 라이브: monitor.json `_turns_summary`(`src/agent/steering/runtime.py:759`)는 per-turn
  `cost_usd` + 집계 `today_cost_usd` 만 — 토큰 필드 없음.

→ 표시 지표(토큰/비용/둘다)와 집계 범위(윈도우/ET세션) 확정 후 TS-only 또는 TS+Python
데몬 변경 범위 결정. 관련: [[opentui-zorder-hittest]], F50(NavRow), F57(NavRow flex/blink).

## Merge Risk Notes
- **공유 파일 (주의)**: `timeline-bar.tsx` — F55(데이마켓 세션 표기)가 같은 파일 region/marker
  로직 수정. 본 트랙은 NavRow(cost/token 라벨) 영역 → 함수 레벨 분리되나 동일 파일이라
  rebase 시 인접 헝크 주의. [[timeline-midnight-crossing-regions]].
- **API/시그니처 변경**: `MonitorTurn` 타입에 토큰 필드 추가 가능(TS). 토큰 지표 선택 시
  `_turns_summary`(Python) recent 블록 + 집계 필드 추가 가능.
- **알려진 동시 변경**: F55, F56 (timeline-bar.tsx 영역 확인 필요).

## Stage Progress
- [x] Workspace Detection — Brownfield, RE 아티팩트 존재 → RE skip
- [x] Requirements Analysis — standard (지표=비용/범위=윈도우 확정; 승인 게이트 대기)
- [x] User Stories — skip (단일 UI 표시 개선, 신규 워크플로 없음)
- [x] Workflow Planning — minimal (단일 단위)
- [x] Application Design — skip (신규 컴포넌트/메서드 없음)
- [x] Units Generation — skip (단일 소규모)
- [x] Construction (single unit — windowed cost in NavRow) — commit f27c0e5
  - [x] windowedCost 순수 헬퍼 + 단위테스트 (8 케이스)
  - [x] NavRow always-show `· $` (isLive gate 제거) + windowCost 배선
- [x] Build & Test — PASS (16 unit tests, timeline-bar/format typecheck clean) → merge-awaiting
