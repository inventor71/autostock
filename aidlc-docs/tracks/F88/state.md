# Track F88 — Agent self-authored long-horizon triggers (macro/news 대기 후 self-wake)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F88
- **Title**: Agent self-authored long-horizon triggers (macro/news 대기 후 self-wake)
- **Type**: feature
- **Status**: merged → main a942390 (2026-06-22)  <!-- rebased 57f7f82→1f594cc (prompts/orchestrator 충돌 해소: F85 disposition + F88 macro_triggers 양립) → merged a942390 -->
- **Branch**: feat/F88
- **Worktree**: .claude/worktrees/F88
- **Submodule branch**: — (monorepo)
- **Base commit**: 57f7f82 (worktree branch-point; main이 F89 머지로 전진)
- **Start Date**: 2026-06-16T03:33:15Z

## Extension Configuration
- **Security Baseline**: **Enabled** (blocking). 적용 룰: SECURITY-05/06/07/09/10/11/13/14/15. 부분: 03/08/12. N/A: 01/02/04 (DB/LB/HTML 서빙 없음). requirements.md §6 매핑 참조.
- **Property-Based Testing**: **Partial** — PBT-02/03/07/08/09 enforce, 나머지 advisory. 프레임워크: Hypothesis. 대상: spec/ctx 직렬화 round-trip, TTL/rate-limit 불변, verdict 파싱.

## Scope
trading agent가 직접 long-horizon trigger를 작성/등록/취소할 수 있게 한다. 장중 wake(급변동/fill/
가격알림)보다 macro한 지표/뉴스를, autostock이 큐레이션하지 않는 것까지 agent가 대기시켰다가 self-wake.

**토의로 락된 핵심 아키텍처 (requirements/design 입력):**
- 트리거 = agent 작성 Python 순수함수 `should_fire(ctx) -> {fire, why}`, `workspace/triggers/<id>/`
  (trigger.md spec + predicate.py + daemon관리 state.json) — journal workspace 패턴 확장.
- 실행 = 일회용 Docker 샌드박스 (기존 docker-verify 하니스 재활용): `src/` 미마운트,
  `--network=none --read-only`, cap-drop=ALL, non-root, no-new-privileges, mem/cpu/pids 상한,
  timeout, 시크릿 제거 env, tmpfs만 쓰기. → 소스 불가시·불변·유출0·시크릿0.
- 데이터 = 브로커드 주입: predicate 네트워크 0. daemon이 선언 소스 대신 fetch → ctx.json ro 주입.
- authoring surface = daemon 호스팅 MCP 서버 (loopback HTTP + 토큰; stdio 아님). tools:
  trigger.register/list/cancel/inspect. agent `claude -p` 세션 .mcp.json 연결.
- control plane(신뢰: daemon MCP + brokered fetch + 평가루프) vs execution plane(불신: Docker predicate) 분리.
- 발화 = wake만: daemon TriggerEvaluator(느린 cadence) 평가 → fire면 rate-limit 후
  `TurnCoordinator.trigger(WakeEvent "agent_trigger")` → wake turn. 매매는 기존 supervisor gate 통과.
- 재활용: WakeDetector/WatchStore/TurnCoordinator (src/agent/intraday/wake.py, steering/turns.py),
  journal workspace, signals collector (macro/movers/earnings/holdings/sentiment).

**requirements/design에서 확정할 남은 결정:**
1. 선언 데이터 소스 카탈로그 (기존 signals + WebSearch 쿼리 + WebFetch allowlist URL)
2. predicate 계약 & AST 스크린 차단 목록
3. lifecycle/limits: TTL 기본·최대, 최대 활성 트리거 수, 발화 rate-limit, 연속에러 자동 비활성화
4. cadence 옵션(15m/hourly/daily) & 병렬 평가 상한
5. wake 프롬프트 트리거 컨텍스트 주입 & 기존 wake와 dedup

## Merge Risk Notes
> Build & Test green(F88 범위) 시점 작성.

- **수정한 공유 파일 (전부 additive, 기존 동작 보존)**:
  - `src/agent/intraday/records.py` — `WakeKind` Literal에 `"agent_trigger"` 추가(additive).
  - `src/agent/prompts.py` — `wake_prompt`에 optional `macro_triggers` param + `macro_triggers_from_events`
    헬퍼 추가. **F85(aggressiveness)가 프롬프트 posture를 건드릴 수 있어 교차 주의** — wake_prompt 충돌 가능.
  - `src/agent/orchestrator.py` — `run_wake`만 수정(macro 추출 주입, additive).
  - `config/config.py` — `triggers: dict={}` 필드 추가(additive).
  - `src/agent/tools/__main__.py` — `trigger` 서브커맨드 추가(additive, 기존 커맨드 무변).
  - `src/trading/modes/agent.py` — `_setup_triggers`/resolver 추가 + steering 블록에 1줄 호출(additive).
    **F86(steering 산출물 엔드포인트)과 같은 파일 교차 가능** — 다른 영역이라 충돌 낮음.
- **신규 (충돌 무관)**: `src/agent/triggers/*`, `tests/triggers/*`.
- **API 변경**: WakeKind 확장(additive), wake_prompt 시그니처에 optional 추가(하위호환). 삭제/리네임 없음.
- **알려진 동시 트랙**: F33(paused), F73(viz-shell), F84/F86(mobile), **F85(prompts/risk — wake_prompt 주의)**.
- **사전 결정**: 머지 시 prompts.py/agent.py를 F85/F86 변경분과 대조(rebase 충돌 시 수동 병합).

## Stage Progress
- [x] Workspace Detection — brownfield, CodeKB 존재(read-only consume), 신규 요청(resume 아님)
- [x] Requirements Analysis — comprehensive (requirements.md). 승인 대기.
- [ ] User Stories — <execute/skip + reason>
- [x] Workflow Planning — workflow-plan.md (승인 대기)
- [ ] User Stories — **skip** (단일 개발자·내부 agent 능력, 다중 페르소나/UAT 없음, 아키텍처 락)
- [x] Application Design — **execute** (standard; application-design.md). 승인 대기.
- [x] Units Generation — **execute** (standard; units.md, U1~U5 + critic 반영 범위). 승인 대기.
- [ ] Construction (per-unit Code Generation)
  - [x] U1 — TriggerStore & spec/schema — **green (56 tests)**, construction/U1/code.md
  - [x] U2 — Sandbox Runner (Docker) — **green (10 isolation tests, real containers)**, construction/U2/code.md
  - [x] U3 — Brokered Fetch — **green (10 tests)**, construction/U3/code.md
  - [x] U4 — TriggerEvaluator & lifecycle — **green (15 tests; intraday 110 regression OK)**, construction/U4/code.md
  - [x] U5 — **authoring surface = CLI 서브커맨드** (MCP에서 변경, critic#1+사용자 재승인) + daemon 배선 — **green (10 tests; triggers 101)**, construction/U5/code.md
- [x] Build & Test — F88 `tests/triggers` **101 passed**; 전체 **1429 passed / 3 failed**(3건은
      `tests/signals/test_sentiment_sweep.py` wallclock-drift, **F88 무관·기존**). build-and-test-summary.md
      + post-merge-guide.md 작성. 커밋·merge-awaiting는 사용자 승인 대기.
