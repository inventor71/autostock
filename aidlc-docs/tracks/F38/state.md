# Track F38 — 운영자 수동 turn 트리거 (research turn 등) steering 명령

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F38
- **Title**: 운영자가 데몬에 research turn(및 잠재적 다른 turn)을 수동 트리거하는 steering 명령
- **Type**: feature
- **Status**: merged → main c395faf (2026-06-03)  <!-- /ai-dlc-merge: rebased onto 7766c6a (F39 머지 반영, mcp-server.ts 자동병합 clean — F39 supervisor-gating + F38 research verb 공존), verify green (pytest 638/0 · operator-console TS 145/0), --no-ff merged -->
- **Branch**: feat/F38 (b215499, b0b1275=F42핫픽스 위 리베이스)
- **Worktree**: .claude/worktrees/F38 (Code Gen Part 2 전 생성)
- **Submodule branch**: — (monorepo, post-F35)
- **Base commit**: f26ab6a (main @ track 생성 시점)
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Disabled (2026-06-03 — 인자 없는 내부 verb, 새 attack surface 없음, 기존 ask-gate 재사용)
- **Property-Based Testing**: Disabled (2026-06-03 — 알고리즘/직렬화 로직 없는 얇은 트리거; 예제 기반 단위 테스트로 충분)

## Scope
운영자가 자동 스케줄(시장 오픈/인터벌)을 기다리지 않고 **수동으로 turn을 트리거**할 수 있는
steering 명령을 추가한다. 동기: today_count==0(오늘 research 미실행)인데 장 마감 등으로
자동 트리거를 기다려야 하고, 운영자가 중간에 추가 research를 시킬 방법이 없다.

핵심 메커니즘(조사 완료):
- `SteeringRuntime`가 `orchestrator`(run_morning_research/run_intraday/run_eod_review)와
  `coordinator`(TurnCoordinator.try_scheduled_turn = skip-if-busy)를 보유 — runtime.py:55,67.
- reconcile_run_fn 주입 패턴(runtime.py:71)을 따라 **turn-trigger 콜백을 CommandHandler에 주입**.
- 새 steering verb 추가(records.py SteeringVerb Literal + commands.py `_v_*` 핸들러).
- 주의: CommandHandler는 CommandBus 워커 스레드에서 실행 → research turn(수 분 소요)을
  워커에서 직접 돌리면 버스가 블록됨. 스케줄 turn처럼 coordinator 경유로 off-thread 실행 필요.
- 콘솔에서 실제 호출하려면 TS측(operator-console mcp-server.ts + zod + opencode permission key)
  배선 필요 — F9/F19/F21 선례. (스코프 질문 대상.)

관련: [[f9-gated-alpaca-orders]], [[f4-steering-runtime-wiring]], [[intraday-redesign]]

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 아티팩트 존재(역공학 skip)
- [x] Requirements Analysis — standard (D1~D4 확정, requirements.md) ✅ 승인 2026-06-03
- [x] User Stories — skip (단일 운영자 명령, 워크플로 단순; FR/AC로 충분)
- [x] Workflow Planning + Application Design — minimal (design-and-plan.md) ✅ 승인 2026-06-03
- [x] Units Generation — skip (단일 유닛)
- [x] Construction (per-unit Code Generation) — 완료, feat/F38 b215499 (b0b1275=F42핫픽스 위, 미머지)
  - [x] C-1 start_async(+on_done)  [x] C-2 SteeringVerb+contract  [x] C-3 _v_research  [x] C-4 runtime wiring
  - [x] C-5 schema.ts  [x] C-6 parser.ts  [x] C-7 mcp-server help  [x] C-8 tests
  - [x] FR-7 완료 푸시 이벤트 (on_done→bus.submit emit_outcome, corr_id 연동, completed/failed)
  - [x] FR-8 수동 research 최우선+큐잉 (start_priority_async; wake/reconcile 양보; 드롭 없음 started/queued)
- [x] Build & Test — PY 121 steering + 164 intraday/wake/turn pass(신규 ~18), TS parser/contract pass, tsc exit 0;
      docker-verify(F38 worktree): build/typecheck(19)/unit(622) green. smoke=실키 필요(대기)
- [x] **Merge hand-off** — Build&Test green → Status `merge-awaiting` 설정, `/ai-dlc-merge` 큐 등록.
      루트 레지스트리 행은 `active` 유지(머지 시 `/ai-dlc-merge`가 `merged` 전환). 직접 main 머지 안 함.
      (alpaca-data.test.ts만 ALPACA env 미설정 실패 — F38 무관/기존)
