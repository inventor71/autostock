# Track F28 — Normal-mode UI self-explanation (agent answers "what is this UI element?")

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F28
- **Title**: Normal-mode 에이전트가 자기 TUI 요소(예: 타임라인 옆 `$6.01`, 마커, 사이드바 블록)의 의미를 설명할 수 있게 — 코드 비공개(normal) 상태에서도 답변 가능한 UI 지식 제공
- **Type**: feature
- **Status**: merged 2026-06-03 (parent d1f72e6+02d6a41, submodule fork main b26a930 [local])
- **Branch**: feat/F28 (TBD)
- **Worktree**: .claude/worktrees/F28 (TBD)
- **Submodule branch**: feat/F28 (likely — TUI/console fork)
- **Base commit**: a4b1732
- **Start Date**: 2026-06-01T11:05:46Z

## Relationship to F26
- **Depends on / rides F26**: F26 normal 프로파일은 `$STEERING_DIR/**`만 read 허용. F28이 UI 지식을 `$STEERING_DIR/`에 두면 **F26 권한 설계를 수정하지 않고** 그대로 읽힌다. (별도 트랙으로 분리한 이유: F26은 권한 레이어, F28은 지식 제공 — 도메인 다름; F26은 이미 설계 승인+단일 응집.) 전달 방식이 system-prompt/MCP면 F26 의존 없음.
- 메커니즘이 prompt/MCP가 아니라 "steering 파일 읽기"라면 F26 머지 이후가 자연스러움(allowlist 필요).
- (주의: F27은 별개 동시 트랙 = docker-verify host-user. 본 트랙은 F28.)

## Scope (잠정 — 요구사항 확정 전)
사용자 요청: normal mode에서 UI 질문에 답하도록. 예) 타임라인 topbar `$6.01`의 의미. 현재 에이전트는 daemon snapshot에 그 데이터가 없어 "모른다"고 답함(스크린샷). 필요한 것: (1) UI 요소의 **정적 의미** 사전 + (2) 가능하면 **현재 값**(예: `$6.01` 실수치 = monitor.json `today_cost_usd` 추정)으로의 매핑.
근거: timeline topbar 코드는 F25 브랜치(active)에만 존재 — 서브모듈 main 미포함. `today_cost_usd`는 runtime.py:381(_turns_summary). F28 discovery에서 F25 코드로 `$6.01` 의미 확정.

## ⏸️ RESUME POINT (/ai-dlc-resume)
**Paused at: Requirements Analysis — awaiting approval.** Requirements doc written at
`aidlc-docs/inception/requirements/normal-ui-help.md`. All design forks resolved (see below).
Next: user approval → Workflow Planning.

## Stage Progress
- [x] Workspace Detection — brownfield; RE artifacts exist
- [x] Requirements Analysis — **APPROVED** 2026-06-02. requirements.md in `aidlc-docs/inception/requirements/normal-ui-help.md`
- [x] User Stories — SKIP (내부 도구, 단일 운영자)
- [x] Workflow Planning — APPROVED 2026-06-02 (`F28-execution-plan.md`)
- [x] Application Design — SKIP (FD에 포함)
- [~] Construction
  - [x] Functional Design — APPROVED 2026-06-02 (critic#1+#2 반영, 정적 의미 사전으로 단순화)
  - [x] Code Generation Part 1 (plan) — APPROVED 2026-06-02 (`ui-legend-code-generation-plan.md`)
  - [x] Code Generation Part 2 (build) — COMPLETE 2026-06-02, worktree `.claude/worktrees/F28`
    - 서브모듈 `feat/F28` `03bc5b1` (tui-trading/AGENTS.md) · parent `feat/F28` `9eefceb` (src/test/json)
    - 정적 ui-legend.json 21엔트리 + parser READ_VERBS + steer-handler 분기 + mcp-server description
    - `bun test ./test/` = **131 pass, 0 fail**. 0 new deps. schema.ts·python 데몬 미변경.
    - gitlink는 머지 시 커밋 (서브모듈 feat/F28 → fork main 먼저).
- [x] Build & Test — COMPLETE 2026-06-02. `build-and-test/ui-legend/build-and-test-summary.md`. 131/0 + 런타임 검증. **머지 승인 대기.**

## Open design forks — ALL RESOLVED (최종, critic 2회 + 단순화 반영)
- **전달**: `steer_read{command:"/ui-legend [element]"}` read verb (F29 codebase 선례). `{view,element}` 파라미터 아님.
- **데이터**: **정적 `ui-legend.json`**(parent repo `operator-console/src/`, 사람 유지, git). TUI 자동생성·fallback 제거.
- **구조**: `{id, meaning, location?}` — `data_source`/현재값 제거(사용자가 화면에서 봄).
- **범위**: 의미만(Q3 현재값 철회). 전체 TUI 커버(Q4=A).
- **변경 표면**: parent `operator-console/src/{parser,steer-handler,mcp-server}.ts` + ui-legend.json. schema.ts·서브모듈·데몬 변경 0.
- Extensions: Security=skip, PBT=skip.
