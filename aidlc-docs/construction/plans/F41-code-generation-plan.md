# F41 — Code Generation Plan

> Track F41 · worktree `.claude/worktrees/F41` (branch feat/F41) · 2026-06-03
> 자율 진행 합의([[feedback-autonomy-construction]]): 설계 승인 후 코드+테스트 자율 실행.

## Unit 1 — `agent-eval-persistence` (Python)
- [x] 1.1 `src/agent/agent_reports.py` 신규 — 스키마 헬퍼: `make_eval`, `build_report`,
      `write_agent_report`(atomic), `read_agent_report`, `has_agent_report`, 파일키(turn_id|ts).
- [x] 1.2 `orchestrator._run_sequential_research` — turn_id 생성, 라운드 결과 수집(initial/debate/synthesis),
      결정 turn_id 태깅, record_turn(summary+turn_id 채움, FR-2), write_agent_report best-effort.
- [x] 1.3 `orchestrator._run_parallel_research` — turn_id 생성, SubAgentReport→AgentEval 변환,
      결정 태깅, record_turn(summary+turn_id), write_agent_report best-effort.
- [x] 1.4 테스트 `tests/agent/test_agent_reports.py` — 라운드트립/atomic/키 fallback.
- [x] 1.5 테스트 orchestrator 캡처 — sequential/parallel 캡처 + FR-2 채움 + best-effort 무영향 (fake runner).
- [x] 1.6 `pytest` 회귀 0.

## Unit 2 — `overlay-drilldown` (Python steering + TS TUI)
- [x] 2.1 ~~steering/runtime.py 변경~~ → 불필요. TUI가 `workspace_root`로 사이드카를 직접 읽음(historical 패턴 재사용). 마스킹은 TS `maskSecrets()`로 노출 지점에 적용(NFR-4).
- [x] 2.2 과거+라이브 모두 `readAgentReport(root, turnId)` 한 경로로 처리(F36 확장점, 파일 직접 읽기).
- [x] 2.3 TS `types.ts` — `AgentEval`/`AgentReport` 타입 + `MonitorTurn.has_agents`.
- [x] 2.4 TS hook/데이터 — turn별 agent report fetch (라이브 monitor + historical 파일).
- [x] 2.5 `turn-overlay.tsx` — agents 목록(라벨+role+status) + synthesis 요약 + drill-down 전문 패널(스크롤/back),
      비-multi-agent fallback(무회귀).
- [x] 2.6 TS 테스트 + `bun run typecheck`.

## 검증
- [x] Python `pytest` (전체) green — 621 passed, 0 regressions.
- [x] `(cd operator-console/cli && PATH=~/.bun/bin:$PATH bun run typecheck)` clean — turbo 19/19.
- [x] tui-trading bun test — 44 pass (agent-report.test 포함).
- [ ] (선택) live read-only 또는 docker-verify로 오버레이 수동 확인 — **사용자 환경에서 가능**(아래 안내).
