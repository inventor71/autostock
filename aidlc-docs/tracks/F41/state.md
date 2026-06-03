# Track F41 — Research turn 마커 오버레이 정보 강화 (multi-agent 평가 노출)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F41
- **Title**: Research turn 마커 오버레이 정보 강화 (multi-agent 평가 노출)
- **Type**: feature
- **Status**: merged → main f330370 (2026-06-03)  <!-- /ai-dlc-merge: rebased onto 7c62527, verify green (pytest 621 · tui-trading 44 · typecheck 19/19), --no-ff merged -->
- **Branch**: feat/F41
- **Worktree**: .claude/worktrees/F41
- **Submodule branch**: — (monorepo, post-F35; touches Python + operator-console/cli)
- **Base commit**: 72aba01
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Disabled (내부 운영자 TUI/저널 개선, 사용자 Q4 미선택). 단 표시 텍스트는 기존 `_mask_secrets` 정책 준수(NFR-4).
- **Property-Based Testing**: Disabled (사용자 Q4 미선택). 스키마 라운드트립은 일반 단위 테스트로 커버.

## Scope
타임라인 마커 클릭 시 뜨는 turn 오버레이가 research turn에 대해 충분히 informative하지 않음
(스크린샷: 헤더 한 줄 + 빈 summary). 두 가지 근본 원인:
1. **multi-agent research turn의 `summary`가 빈 문자열** — `orchestrator._run_sequential_research` /
   `_run_parallel_research`의 `record_turn(...)` 호출이 `build_turn_summary(...)`를 거치지 않음
   (단일 세션 `_run` 경로만 summary를 채움). 06-02 스크린샷 turn이 정확히 이 케이스.
2. **sub-agent별 평가가 어디에도 영속되지 않음** — parallel 모드의 `SubAgentReport.result_text`는
   synthesis 프롬프트에 쓰인 뒤 워크스페이스와 함께 삭제됨. sequential 모드는 한 세션의 R1→R2→R3
   라운드라 "agent"가 분리돼 있지 않고, 라운드별 추론은 `workspace/daily/<date>.md` 내러티브에만 존재.

목표: 마커 클릭 시 (a) summary 버그 수정, (b) N개 agent/라운드가 있었으면 각 agent의 평가/판단을
오퍼레이터가 볼 수 있도록 영속 + 오버레이 표시. 데이터 소스/표시 깊이/오버레이 UX는 요구사항 분석에서 확정.

관련 메모리: [[feedback-ui-concretization]] (UI는 질문으로 구체화), [[feedback-korean-aidlc-docs]],
F22/F23/F25/F36 (멀티에이전트 리서치 + 타임라인 오버레이 선행 트랙).

## Stage Progress
- [x] Workspace Detection — Brownfield, 기존 프로젝트 (reverse-engineering 아티팩트 존재)
- [x] Requirements Analysis — Standard depth, **승인 2026-06-03** (inception/requirements/F41-research-turn-overlay.md)
- [ ] User Stories — SKIP (내부 운영자 TUI/저널 개선, 사용자 대면 신규 워크플로 없음)
- [x] Workflow Planning — **승인 2026-06-03** (inception/plans/F41-workflow-plan.md)
- [ ] Application Design — SKIP (→ Functional Design에서 영속 스키마 설계)
- [ ] Units Generation — SKIP (워크플로 계획에 유닛 정의)
- [x] Construction (per-unit Code Generation)
  - [x] Unit 1 `agent-eval-persistence` — FD 승인 → Code Gen 완료. `src/agent/agent_reports.py` 신규 + orchestrator 두 경로 캡처 + record_turn summary/turn_id 버그수정. test_agent_reports.py 10건. 커밋 `feat(F41) Unit1`.
  - [x] Unit 2 `overlay-drilldown` — FD(lite) → Code Gen 완료. TS `readAgentReport`/`maskSecrets`, drill-down `turn-overlay.tsx`, types, session route prop. runtime.py 변경 불필요(TUI 직접 읽기). agent-report.test.ts (tui-trading 44 pass). 커밋 `feat(F41) Unit2`.
- [x] Build & Test — Python `pytest` 621 passed(0 regress) · console turbo typecheck 19/19 · tui-trading bun test 44 pass. (선택 live/docker 수동 오버레이 확인은 사용자 환경에서 가능)
- [x] Merge hand-off — Status=`merge-awaiting` (Build&Test 통과). 직접 main 머지하지 않음; `/ai-dlc-merge` 큐에서 rebase→verify→merge→cleanup 후 레지스트리 `merged` 전환. 2 커밋 on feat/F41 (Unit1, Unit2).
