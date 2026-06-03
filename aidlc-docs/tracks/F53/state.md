# Track F53 — MCP Position Thesis 노출 (TUI에서 agent position thesis 확인)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F53
- **Title**: MCP Position Thesis 노출 — TUI에서 agent position thesis 확인
- **Type**: feature
- **Status**: merged → main 621b227 (2026-06-04)
- **Branch**: feat/F53
- **Worktree**: .claude/worktrees/F53
- **Submodule branch**: —
- **Base commit**: a8957ad
- **Merge commit**: d3a04dd
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Enabled (Full). Applicable: SECURITY-03 (no secrets in logs), SECURITY-15 (fail-closed error handling). N/A: SECURITY-01/02/04-14 (no cloud infra, DB, web, or user auth in scope).
- **Property-Based Testing**: Enabled (Partial). Applicable: PBT-02, PBT-03, PBT-07, PBT-08, PBT-09 — 순수 함수 및 직렬화 round-trip only. Framework: Hypothesis. N/A for this track (pure file I/O passthrough, no business logic).

## Scope
현재 TUI에서 `autostock_get_all_positions` 등으로 포지션을 조회할 때 브로커 기준 포지션(수량, 평단가, 현재가, 손익)만 보여주고, 에이전트가 `workspace/positions/*.md`에 기록하는 포지션 테제(position thesis) 정보는 노출되지 않음. MCP 툴을 업데이트하여 TUI에서도 에이전트의 포지션 테제(매수/보유 이유, 전략, 판단 근거 등)를 함께 확인할 수 있도록 개선.

### 구현 내용
- `steer_read /thesis <SYMBOL>` — `workspace/positions/<SYMBOL>.md` markdown 전문 반환
- `steer_read /theses` — thesis 파일이 있는 모든 symbol 목록 반환
- TypeScript MCP 서버 5개 파일 변경 (filedrop, steer-handler, parser, schema, mcp-server)
- 데몬 변경 없음 — MCP 서버가 workspace/positions/ 직접 읽기

## Merge Risk Notes
- **공유 파일 (주의)**: `operator-console/src/schema.ts`, `operator-console/src/parser.ts` — 다른 active 트랙이 같은 파일을 건드리면 conflict 가능 (F51, F52는 investigation-only라 충돌 가능성 낮음)
- **API/시그니처 변경**: 없음 — `SteeringVerb`에 2개 항목 추가(read-only), 기존 API 불변
- **알려진 동시 변경**: 없음

## Stage Progress
- [x] Workspace Detection — Brownfield, Reverse Engineering artifacts exist, skipped RE
- [x] Requirements Analysis — Standard depth, approved
- [x] User Stories — SKIP (내부 개선, 단일 운영자, 신규 사용자 워크플로 없음)
- [x] Workflow Planning — approved
- [x] Application Design — SKIP (신규 컴포넌트 없음, 기존 SteeringRuntime 경계 내)
- [x] Units Generation — SKIP (단일 단순 유닛)
- [x] Construction — Code Generation
  - [x] Part 1 — Plan approved
  - [x] Part 2 — Implementation (commit d3a04dd)
  - [x] Functional Design — SKIP
  - [x] NFR Requirements — SKIP
  - [x] NFR Design — SKIP
  - [x] Infrastructure Design — SKIP
- [x] Build & Test — ALL GREEN
  - TypeScript: 46 tests (38 existing + 8 new), typecheck 19/19
  - Python: 680 tests, 0 regressions
