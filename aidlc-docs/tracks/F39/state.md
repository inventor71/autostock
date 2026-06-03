# Track F39 — Normal 모드 코드 질문 차단 (supervisor 아닐 때 소스/내부 구현 질문 거부)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F39
- **Title**: Normal 모드에서 운영자 콘솔 에이전트가 코드/소스 내부 질문에 답하지 않도록 차단 — supervisor 모드 아닐 때 코드 읽기 시도·추측 금지, 운영 질문은 steering 데이터로 응답
- **Type**: feature (behavior hardening)
- **Status**: merge-awaiting (commit 6ba79d1 on feat/F39, base 72aba01; ↑1 over main — `/ai-dlc-merge` 큐 등록)
- **Branch**: feat/F39 (6ba79d1)
- **Worktree**: .claude/worktrees/F39
- **Submodule branch**: — (monorepo, post-F35: `operator-console/` is a normal in-repo dir)
- **Base commit**: 72aba01
- **Start Date**: 2026-06-03T09:59:40Z

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | **Yes** | Requirements Analysis (2026-06-03) |
| Property-Based Testing | **No** | Requirements Analysis (2026-06-03) |

- **Security Baseline (ENABLED)**: 적용 — SECURITY-03(거부/트리 메시지에 비밀·경로 노출 금지),
  SECURITY-15(`/codebase` 게이팅 fail-closed). 노출 표면을 좁히는 변경이라 새 비밀 노출 없음. 나머지 N/A.
- **Property-Based Testing (DISABLED)**: 프롬프트/설정 + 단순 게이팅 분기 → 알고리즘 로직 없음.

## Confirmed Requirements (2026-06-03)
- **Q1=A** 소스/구현 내부 질문만 거부; 운영/런타임 질문은 steer_read 데이터로 계속 응답(소스 추측 금지).
- **Q2=A** 프롬프트 가드 + 구조적 차단(defense-in-depth).
- **Q3=A** `/codebase` 트리 supervisor 전용(normal 차단).
- **Q4=B** 거부 메시지에 supervisor 미언급(개발자 전용 숨김) → Q2/Q3의 "supervisor 안내" 문구 무효.
- **Q5** Security Baseline=Enabled, PBT=Disabled.
- 요구사항 문서: `aidlc-docs/inception/requirements/F39-normal-mode-code-block.md` (FR-1..6, NFR-1..3).

## Scope
운영자 콘솔(opencode 포크) 에이전트가 **supervisor 모드가 아닌 normal 모드**일 때, 소스 코드/구현 내부에
대한 질문에 **아예 답하지 않도록** 동작을 강화한다.

관측된 문제 (사용자 transcript, normal 모드):
- 에이전트가 `autostock_steer_read [command=/codebase]`로 프로젝트 트리를 받고, `src/agent/orchestrator.py`/
  `steer-handler.ts`를 직접 `Read` 시도(권한으로 차단됨) → 그럼에도 **코드 구조를 추측해 코드 레벨 분석 답변**을 함.
- 즉 **권한 벽(F26)은 동작**하지만, 에이전트가 코딩 어시스턴트처럼 (1) 소스 읽기를 *시도*하고 (2) 트리/추측으로
  코드 내부를 *설명*한다.

근본 원인 (inception 중 코드 확인):
- 운영자 에이전트에 **autostock 전용 페르소나/시스템 프롬프트가 없음** → opencode 기본 코딩 어시스턴트 프롬프트로
  동작하므로 소스 읽기·내부 설명을 당연하게 시도.
- `autostock_steer_read`(= `/codebase` 프로젝트 트리 포함, F29)가 `opencode.json`에서 **두 프로필 모두 `allow`** →
  normal 모드에서도 코드 구조를 받아 추론 가능.

관련 트랙/메모리: F26(supervisor 권한 프로필), F28(normal-mode `/ui-legend`), F29(supervisor codebase
orientation), [[steering-console-redesign]], [[f4-steering-runtime-wiring]].

## Stage Progress
- [x] Workspace Detection — brownfield; RE 아티팩트 존재 → reverse-engineering skip
- [x] Requirements Analysis — Standard depth, APPROVED 2026-06-03 ("계속진행"). 문서 F39-normal-mode-code-block.md
- [x] User Stories — SKIP (단일 운영자 페르소나, 동작/설정 변경)
- [x] Workflow Planning — plan: inception/plans/F39-execution-plan.md (awaiting approval)
- [x] Application Design — SKIP (새 컴포넌트 없음)
- [x] Units Generation — SKIP (단일 응집 변경)
- [x] Construction (per-unit Code Generation) — unit `normal-mode-code-block` (worktree `.claude/worktrees/F39`, feat/F39)
  - [x] Functional Design — light (plan §3: 거부 경계 스펙 + carrier 결정)
  - [x] NFR Requirements — SKIP (0 new deps)
  - [x] NFR Design — SKIP
  - [x] Infrastructure Design — SKIP
  - [x] Code Generation — L1 프롬프트 가드(operator.md + normal-guard.md + launcher가 OPENCODE_CONFIG_CONTENT로
    프로필별 instructions 주입) + L2 `/codebase` supervisor 게이팅(steer-handler fail-closed, mcp.environment에
    AUTOSTOCK_SUPERVISOR 전달, mcp-server 설명 조건부). critic 5건 반영(AR-1/AR-2).
- [x] Build & Test — operator-console `bun test` 107 pass; verify-lockdown(2-profile) **PASS**; registry.test **16 pass**.
- **Status: merge-awaiting** — feat/F39 @ 6ba79d1 커밋 완료(↑1 over main, working tree clean). main 직접 머지 안 함;
  `/ai-dlc-merge` 큐에서 처리(rebase·verify·merge·cleanup). 레지스트리 행은 머지 전까지 `active` 유지(컨벤션).

## Implementation Summary (2026-06-03)
- **신규 2** `operator-console/prompts/operator.md`(페르소나, 두 프로필), `normal-guard.md`(normal 거부 규칙).
- **수정 4** `launcher/config.ts`(buildInstructions + consoleEnv OPENCODE_CONFIG_CONTENT 주입),
  `cli/.opencode/opencode.jsonc`(mcp.environment에 AUTOSTOCK_SUPERVISOR), `src/steer-handler.ts`(handleSteerRead
  supervisor 파라미터 + `/codebase` fail-closed 게이팅), `src/mcp-server.ts`(supervisor 계산/전달 + CODEBASE 설명 조건부).
- **테스트** launcher(F39 3) + steer-handler(F39 3) 신규; 107 pass / verify-lockdown PASS / registry 16 pass.
- **0 new runtime deps**. critic: AR-1(프리폼 추론 L1-only), AR-2(supervisor=개발자 신뢰경계) 수용.
