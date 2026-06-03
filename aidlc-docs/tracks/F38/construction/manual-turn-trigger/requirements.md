# F38 — 운영자 수동 turn 트리거 (research) 요구사항

> Track F38. Type: feature. Depth: standard. 작성일 2026-06-03.
> 관련 메모리: [[f9-gated-alpaca-orders]], [[f4-steering-runtime-wiring]], [[intraday-redesign]].

## 1. 배경 / 동기
운영자가 콘솔(`autostock_steer_read`)로 `/turns`·`/status`를 조회한 결과 `today_count: 0`
(오늘 research turn 미실행)인데, 데몬의 turn은 시장 오픈/인터벌 등 **자동 스케줄로만** 돈다.
중간에 운영자가 직접 research를 더 시킬 수단이 없다. → on-demand 트리거 명령을 추가한다.

## 2. 확정된 설계 결정 (질문 게이트, 2026-06-03)
| # | 질문 | 결정 |
|---|------|------|
| D1 | Turn 종류 범위 | **research만** (verb 1개) |
| D2 | 가드 동작 | **스케줄 turn과 동일** — `paused`면 실행 안 함, 다른 turn 진행 중이면 skip-if-busy, `market_open` 무관(research는 원래 프리마켓 실행) |
| D3 | 중복 실행 (today_count>0) | **항상 허용** — 운영자가 명시적으로 시킨 것이므로 매번 실행 |
| D4 | 콘솔 배선 범위 | **데몬+콘솔 풀배선** — 운영자가 `autostock_steer`로 바로 호출 가능 |

## 3. 기능 요구사항 (FR)
- **FR-1**: 새 steering verb **`research`** 추가. 인자 없음. 운영자가 1회 호출하면 데몬이
  morning research turn 1회를 실행한다.
- **FR-2 (가드, D2)**: 핸들러는 스케줄 research(`_premarket_research`)와 동일한 가드를 적용한다.
  - `state.run_state().paused == True` → 실행하지 않고 `deferred`/`skipped` 결과를 emit.
  - 실행은 `coordinator.try_scheduled_turn(orchestrator.run_morning_research)` 경유 → 다른
    turn/reconcile 진행 중이면 **skip-if-busy**(큐잉하지 않음, 안내만).
  - `market_open` 조건은 **검사하지 않는다**(프리마켓 research 허용).
- **FR-3 (중복, D3)**: `today_count`와 무관하게 매 호출 실행. 사전 차단 없음.
- **FR-4 (논블로킹)**: research turn은 수 분 걸릴 수 있다. CommandHandler는 **CommandBus 워커
  스레드**에서 도므로, turn을 워커에서 직접 동기 실행하면 다른 steering 명령이 그동안 블록된다.
  → 트리거는 turn을 **off-thread(coordinator 경유)** 로 시작하고 즉시 결과를 emit해야 한다
  (실제 turn 완료를 기다리지 않음; 완료는 turns.jsonl/telemetry로 관측).
- **FR-5 (결과/감사)**: 다른 verb와 동일하게 `_emit`으로 outcome 이벤트 + `human_directives.jsonl`
  InterventionRecord 기록. outcome 예: `triggered`(시작됨) / `skipped`(busy) / `deferred`(paused).
- **FR-6 (콘솔, D4)**: 운영자가 `autostock_steer`로 호출 가능하도록 TS측 배선.
  - `operator-console/src/schema.ts` `SteeringVerb`에 `research` 추가.
  - `operator-console/src/parser.ts` lifecycle case에 `research` 추가
    (deterministic 슬래시 shorthand `/research`, 인자 없음, confirm-required).
  - `mcp-server.ts` 도구 설명 help 텍스트(LIFECYCLE/OTHER 줄)에 `/research` 노출.
  - **새 opencode permission key 불필요**: `/research`는 기존 단일 `autostock_steer` 슬래시
    도구를 그대로 통과(이미 `ask`-gated). (place_order류만 별도 MCP 도구라 별도 키가 필요했음.)

## 3.5. 관측성 — 완료 푸시 이벤트 (FR-7, 2026-06-03 추가)
운영자가 트리거 후 turn을 관찰하고 완료 결과를 받아야 한다(사용자 요청).
- **이미 동작(스케줄 경로 재사용 효과)**: 진행 중 turn은 `monitor.json.current_turn`
  (`_on_turn_start`→`set_current_turn` / `_on_turn_end`→`clear_current_turn`)으로 노출,
  완료 결과는 `turns.jsonl`(record_turn, 결정 수)로 적재 → `/turns` today_count++.
- **FR-7 (신규)**: 수동 트리거 turn이 끝나면 **트리거 명령 id와 correlated된 완료 outcome
  이벤트**를 emit한다 — 성공 `completed`: "research turn complete: N decision(s), K in-universe
  (Ts)", 실패 `failed`: "research turn failed: <error> (Ts)". 운영자는 폴링 없이 결과 보고를 받는다.
  - 완료 emit은 **bus 워커**에서 실행(`bus.submit` 경유) — 채널 단일 writer 불변식 유지.
  - `on_done(result, error)`는 **turn_lock 보유 중** 호출 → post-turn 상태(orchestrator
    last_new_decisions/last_kept) 안정 후 카운트 산정.

## 3.6. 우선순위 — 수동 research 최우선 + 큐잉 (FR-8, 2026-06-03 추가)
관측 중 발견: WakeDetector(`wake.py:83`)가 `ReconcileWorker`를 `kind="wake"`로 트리거 →
wake 턴이 reconcile과 **같은 우선 레인** 사용. 그래서 D2의 "스케줄과 동일 skip-if-busy"는
**자동 wake/reconcile이 대기만 해도 수동 `/research`를 드롭**시킴 (운영 중 실제 관측: 모든 최근
턴이 wake라 매번 `skipped: reconcile_waiting`).
- **FR-8 (D2 개정)**: 수동 `/research`는 **최우선 + 큐잉(드롭 없음)**.
  - `TurnCoordinator.start_priority_async`: manual waiter 등록 → `try_scheduled_turn` **및**
    `reconcile_turn`이 양보. 턴락을 **블로킹 획득(off-thread, bounded)** → 진행 중 턴이 끝나면
    즉시 실행. 반환 `"started"`(즉시) / `"queued"`(진행 중 턴 뒤). **절대 드롭/skip 안 함.**
  - `reconcile_turn`은 queued manual을 **bounded-wait**한 뒤 실행(드롭 아님) → 순서 manual→reconcile.
  - CommandBus 워커는 안 막힘(대기는 별 스레드). 단일 세션 직렬화(NFR-1)는 turn_lock으로 유지.
- **안전(NFR-1 연장)**: wake를 뒤로 미뤄도 **기계적 보호(resting bracket/OCO + 폴링 청산)는 LLM
  턴과 독립 실행** → 리스크 구멍 아님. wake는 debounce로 재발화.
- _v_research 결과: `started`→`triggered`, `queued`→`queued` outcome.

## 4. 비기능 요구사항 (NFR)
- **NFR-1 (안전/격리)**: turn 트리거는 책(book)을 직접 변경하지 않는다(research는 decision만 작성,
  실행은 오픈 시점). 가드는 스케줄 경로와 1:1 동일 — 새로운 우회 경로를 만들지 않는다.
- **NFR-2 (워커 보호, BR-8.2)**: 핸들러 예외가 CommandBus 워커를 죽이지 않는다(기존 `handle`
  try/except 재사용).
- **NFR-3 (cross-language 계약)**: 인자 없는 verb이므로 zod 스키마 추가 불필요. SteeringVerb
  Literal만 Python(records.py)·TS(schema.ts) 양쪽에 동기화.

## 5. 범위 밖 (Non-goals)
- intraday/eod/wake 수동 트리거 (D1 — 추후 별도 트랙에서 `/run-turn <type>`로 일반화 가능).
- turn 완료를 동기로 기다려 결과를 콘솔에 반환하는 것(FR-4 논블로킹과 상충).
- `force`(paused 무시) 옵션 (D2 — 스케줄 동일 가드).

## 6. 수용 기준 (AC)
- AC-1: `paused=false`에서 `/research` 호출 → 데몬 로그에 research turn 시작, turns.jsonl에
  새 research turn 1건 추가, today_count 증가.
- AC-2: `paused=true`에서 호출 → turn 미실행, `deferred`(paused) outcome.
- AC-3: 다른 turn 진행 중 호출 → `skipped`(busy) outcome, 중복 turn 없음.
- AC-4: 호출 직후 CommandBus가 막히지 않고 후속 steering 명령이 정상 처리(논블로킹).
- AC-5: today_count>0 상태에서 재호출 → 또 1건 실행(중복 허용).
- AC-6: 콘솔에서 `/research` 입력 → opencode가 confirm을 묻고, 승인 시 데몬에 전달.
