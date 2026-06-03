# Functional Design — 비즈니스 로직 모델 (Intraday 루프 재설계 F3)

> 기술-비종속. **흐름·파이프라인·연동**을 정의. 엔티티는 domain-entities.md, 규칙은 business-rules.md.
> 결정: Q1=A, Q2=A,B, Q3=A, Q4=A(i), Q5=A, Q6=A, Q7=B, Q8=B.
> 베이스: main `src/agent/steering/`(F4) — 동시성/JSONL/snapshot 골격 기이행, F3는 그 위에 brief·wake 소스·news·watch만 추가.

---

## BLM-0 — 전체 그림 (한 문단)

데몬 안에 (1) **주기 감지 루프**(시장데이터 직접 + snapshot 캐시 읽기)가 wake 조건을 평가해 WakeEvent를 만들고, (2) 충족 시 **단일 wake turn**을 `ReconcileWorker.trigger(kind="wake")`로 우선 발화하며, (3) 15분 **스케줄 turn**은 `try_scheduled_turn`으로 점유 중이면 스킵, 아니면 실행한다. 모든 turn은 Python이 조립한 **IntradayBrief**를 프롬프트에 받아 재계산 없이 판단한다. LLM이 내는 결정은 종전처럼 `decisions.jsonl`→RiskManager→Broker로만 흐른다(불변). agent는 `watch set/clear` 도구로 감시 조건을 등록하고, Python이 그걸 평가해 wake한다.

```
                 ┌──────────────────── daemon ────────────────────┐
 data_provider ─▶│  WakeDetector(주기) ── WakeEvent[] ─┐           │
 (시장데이터 직접) │      ▲ snapshot 캐시(fills/pos)     │ coalesce  │
                 │      │                              ▼           │
 snapshot(bus)──▶│  BriefAssembler ──IntradayBrief──▶ ReconcileWorker.trigger(kind="wake")
                 │                                     │   └▶ reconcile_turn(turn_lock)
 watch.jsonl ───▶│  WatchEvaluator                     │                                  │
 (agent도구 write)│                                     ▼                                  │
                 │  scheduler 15min ─▶ try_scheduled_turn(turn_lock)  ─(skip if busy)─     │
                 └────────────────────────────────────────────────────────────────────────┘
                                LLM turn ─▶ decisions.jsonl ─▶ gate ─▶ RiskManager ─▶ Broker (불변)
```

---

## BLM-1 — Brief 조립 파이프라인 (FR-2, C-7 입력 분리)

`BriefAssembler.build(symbols) -> IntradayBrief`:

1. **시장 데이터(데몬 직접)**: 종목별 현재가/세션 고저/거래량 페이스를 `data_provider`에서 직접 조회(C-7 — bus 불필요).
2. **플랜 레벨**: 저널/플랜에서 stop/target/entry + E1 active WatchTrigger level을 모아 **각 레벨까지 거리(%)** 계산(`review.outcome_lines` 패턴 재사용).
3. **account/체결(snapshot 캐시만)**: `SteeringState.snapshot()`에서 positions/open_orders/**fills 이벤트**를 읽음(NFR-2; broker 직접 호출 없음). **⚠ `outcome_lines` 호출 금지**(critic#6): `review.outcome_lines`는 `broker.get_position`을 직접 부르므로(`review.py:42`) 그 함수/데이터-조립 방식을 재사용하지 않는다. 포맷 형태만 참고하고, 데이터는 snapshot에서 받는 *별도 포맷터*로 직렬화.
4. **사람 컨텍스트(신규, critic#1)**: `SteeringState`의 활성 directive·대기 승인(pending)·종목 락을 brief에 포함. **F4는 이걸 `run_reconcile`에만 주입**(`_recent_context`, `runtime.py:75`)하고 intraday/스케줄/wake엔 **안 한다**(`_with_human_context` prepend는 **부재**). → F3가 직접 담는다.
5. **델타(E4)**: 직전 turn 발행 snapshot 대비 SnapshotDelta(신규 체결 이벤트/새 고저/레벨 근접 변화).
6. **뉴스 diff(E5)**: 스케줄 turn에 한해 NewsDiff 주입(wake turn은 생략 — 지연 비치명적·E5는 트리거 아님).
7. **렌더(Q6=A)**: 종목별 1~2줄 컴팩트 텍스트 블록으로 직렬화.

> **배선 포인트(critic#8 — "주입만 추가"는 과소평가)**: `_intraday`는 `run_intraday`를 **인자 없이** 호출(`agent.py:110`)하므로 `quotes`는 항상 `None`(`orchestrator.py:112`) — 공백 줄 문제는 실재. F3는 **(a)** `run_intraday`/`intraday_prompt` 시그니처를 brief 받도록 확장 + **(b)** 호출부(`agent.py:110`)가 BriefAssembler 결과를 넘기도록 수정 + **(c)** BriefAssembler 신규 — 셋 다 배선해야 함(단일 변경 아님).

조립 실패는 best-effort: 특정 섹션 누락 시 그 줄만 비우고 turn은 진행(NFR-4).

---

## BLM-2 — Wake 감지 루프 (FR-4, Q5=A coalesce, C-4 연동)

`WakeDetector` — 짧은 주기(브리프/snapshot bus job 결에 맞춤; 예 5초)로 도는 감지기:

1. **입력 수집**:
   - 시장데이터(가격/거래량) ← data_provider 직접(C-7).
   - account/fills ← snapshot 캐시(NFR-2).
   - watch 조건 ← E1 active WatchTrigger(WatchEvaluator).
2. **조건 평가 → WakeEvent[] 생성**:
   - **new_fill**(FR-4-A): snapshot fills 커서 전진분 → FillDelta → WakeEvent(kind=new_fill). (Q3=A)
   - **abnormal_move**(FR-4-C): AbnormalMoveSignal(ATR k·vol m, Q4) → WakeEvent(kind=abnormal_move, entry_inducing=상승 모멘텀 여부 표기).
   - **watch_trigger**(FR-4-D): WatchEvaluator가 충족 조건 발견 → WakeEvent(kind=watch_trigger, payload=WatchTrigger.id).
   - **protective_reassess**(FR-4-E): 보호선 체결/임박(손절 후 재진입 판단 필요) → WakeEvent(kind=protective_reassess).
3. **RunState 게이팅(FR-7, BLM-7)**: paused면 발화 보류(보류 로그) — **게이트는 발화 직전 감지기에서**(C-8: orchestrator 호출 전 early-return이 아니라 감지기 책임). **entries_halted면(Q7=A) `entry_inducing=True` WakeEvent는 발화하지 않는다**(억제) — new_fill·protective_reassess·SELL성 watch는 항상 통과. (gate는 entries_halted를 안 보므로 — critic#4 — 억제는 여기서만 일어난다.)
4. **Coalesce(Q5=A)**: debounce 창 안의 모든 WakeEvent를 **하나의 wake turn**으로 합쳐 발화. **⚠ critic#2 — main `ReconcileWorker` 그대로는 안 됨**:
   - 버퍼: WakeDetector가 **자체 typed-event 버퍼**를 소유. `ReconcileWorker._pending[kind]`는 kind별 **최신 run_fn 1개만** 유지(`turns.py:98`)하므로, 이벤트를 dict에 넣으면 trigger 사이 이벤트가 유실 → **발화 시점(run_fn 안)에 버퍼를 drain**한다(trigger 시점 아님).
   - 타이머/굶김: debounce 타이머가 **kind 공유**(`turns.py:99-101`)라 5초 wake 스트림이 타이머를 계속 취소→`_pending["human"]` 사람 reconcile이 무한 지연. `_fire`도 kind 순차 실행(`:110`)이라 600s 타임아웃 wake가 뒤의 human을 막음. → **수정 필요**: wake 레인과 human 레인의 **타이머 분리**(또는 kind별 타이머) + wake `reconcile_turn` 타임아웃 단축. (이는 ReconcileWorker *수정*이며 순수 재사용 아님 — C-1처럼.)
5. **발화**: run_fn = "버퍼 drain → brief 조립 → wake 프롬프트(사유 목록 포함) → `coordinator.reconcile_turn` 봉투". turn_lock 경유(NFR-1), 다음 스케줄 turn보다 우선.

> wake 프롬프트는 사람-개입용 `reconcile_prompt`가 아니라 **intraday/brief 기반 + 트리거 사유** 전용 프롬프트(FR-4 마지막 줄). 신규 `wake_prompt(brief, events)`.

---

## BLM-3 — 스케줄 15분 turn cheap화 (FR-3, C-1 기이행)

`scheduler 15min job`:
1. brief 조립(BLM-1) → `coordinator.try_scheduled_turn(run_fn)` 호출(run_fn이 brief를 주입한 intraday 프롬프트로 LLM turn).
2. **skip-if-busy(C-2)**: try_scheduled_turn은 turn in-flight 또는 reconcile waiting이면 `("skipped", reason)` 반환 — 큐잉 아님(C-1, main 기이행: `turns.py:37`). 14분에 깬 wake turn이 15분 슬롯과 겹치면 스케줄 발화 스킵.
3. back-to-back(직전 turn이 슬롯 직전 종료)은 허용 — 정상.
4. **사람 컨텍스트 brief에 포함**(critic#1): `_with_human_context` prepend는 **존재하지 않음** — 스케줄 intraday turn은 현재 사람 컨텍스트를 0으로 받는다. → BriefAssembler(BLM-1 step 4)가 directives/pending/locks를 담는다. (재사용 아님, 신규.)
5. paused면 스케줄 경로의 기존 `_paused()`(F4, `agent.py:55-56,107`)가 보류 — 신규 아님(검증됨).

> **F3 변경 범위(critic#8)**: 스케줄 동시성 골격은 main `try_scheduled_turn`(`agent.py:70`, `_scheduled_turn` 내부) 그대로. 단 `_intraday`가 `run_intraday`를 **인자 없이** 호출(`agent.py:110`)하므로 F3는 brief 빌더 + 시그니처 + 호출부 + 사람-컨텍스트를 배선해야 함("주입만"이 아님).

---

## BLM-4 — watch.jsonl 수명주기 (FR-1/FR-5, Q1=A, Q2=A,B, C-5 재사용)

1. **등록(write)**: agent가 LLM turn 중 **도구 `watch set <symbol> <condition> <level> [intent] [valid_until]`** 호출 → 도구가 검증(조건 v1 4종/숫자 level/ET date) 후 `workspace/watch.jsonl`에 append. `watch clear <id>`는 cleared 마킹(append). **agent는 파일 직접 쓰지 않음**(Q1=A — 도구가 유일 writer, advisor-only 경계).
2. **평가(read)**: WatchEvaluator가 `jsonl.read_complete_lines` + ByteCursor로 active 트리거를 읽어(C-5 재사용) 조건 평가.
   - `price_above`/`price_below`: 현재가 즉시 비교.
   - `close_above`/`close_below`: **마감 확정 바**에서만(세션/바 종가) 비교 — 즉시가로 발화하지 않음(Q2=B 의미).
3. **발화**: 충족 → WakeEvent(kind=watch_trigger) → BLM-2 coalesce → wake turn → **LLM이 ADJUST_STOP 여부 판단·기록**(FR-5; Python은 감지만, 결정은 LLM, advisor-only).
4. **fired 추적(critic#5 — ByteCursor 아님)**: 읽기 위치는 `ByteCursor`(파싱 진행)지만, **발화 여부는 별도 `{et_date, fired_ids:set}` 영속 구조**로 기록(ByteCursor는 날짜 스코프·id-set을 표현 못 함). 발화 시 id 추가 → 재시작·재평가 후 재발화 금지. 동일 트리거 하루 1회.
5. **만료(valid_until)**: ET 자정 `daily_sweep`(main `sweep_expired` 패턴에 합류)이 valid_until 경과 트리거를 expired 처리하고, **같은 sweep가 `et_date` 전환 시 `fired_ids`를 초기화**한다(읽기 ByteCursor는 0으로 되돌리지 않음 — append-only 파일의 단조 오프셋 유지).

---

## BLM-5 — 뉴스 diff 폴링 (FR-6, Q8=B, C-6 신규)

1. **대상**: 보유 + watch 등록 종목(Q8=B)의 합집합.
2. **폴링**: 별도 스레드(또는 bus job), 주기 TTL ≥ 15분(`news_provider` 15분 캐시 존중 — 더 자주 돌아도 무의미). best-effort(NFR-4 — 레이트리밋/예외 무시하고 계속).
3. **diff**: per-symbol `last_seen_key`(영속)와 비교해 **신규 헤드라인만** NewsDiff(E5)에 적재.
4. **주입**: 스케줄 turn brief에만(BLM-1 step 5). **wake 트리거 아님** — 신규 뉴스는 다음 스케줄 turn에서 thesis 재평가로 흡수(죽어 있던 catalyst 분기 부활).

---

## BLM-6 — snapshot fills 커서 확장 (C-3 잔여, FR-4-A)

main `runtime.publish_snapshot`(positions+open_orders+market_open, 5초 bus job — `agent.py:181`/`runtime.py:102-123` 검증됨)에 **체결 이벤트 추가**:
1. broker 포트에 **`get_fills(since)` 신규**(Q3=A, critic#3) — **`GetActivitiesRequest(activity_types=[FILL])`** 기반(기존 `_alpaca_fills`의 주문단위 `get_orders` 아님 — 부분체결·OCO·동일수량 교차를 잡으려면 활동내역 필수).
2. publish_snapshot이 activities `since` 커서를 전진시키며 **신규 체결 이벤트 목록**을 snapshot 페이로드에 적재(positions/open_orders와 동일 `atomic_write_text`, `channel.py:181`).
3. WakeDetector(BLM-2)와 BriefAssembler(BLM-1)는 snapshot의 체결 이벤트를 읽어 new_fill wake·델타 줄을 만든다 — **broker를 직접 호출하지 않음**(NFR-2; 확장은 snapshot 페이로드 dict에 키 추가뿐이라 단일워커 불변식 유지).
4. activities 커서는 단조 전진·idempotent(같은 activity `id` 재wake 금지) — 체결 이벤트 id 기반이라 부분체결이 합쳐지지 않음.

> 이것이 현행 META 체결 추론 버그(시세 저가 $630 터치로 추론)를 **broker 진실**로 대체하는 경로다.

---

## BLM-7 — RunState 게이팅 (FR-7, Q7=B, C-8)

발화 직전(감지기/워커에서):
- **paused**: 모든 LLM 발화 보류 + **보류 사실 최소 로그**(BLM-2 step 3; orchestrator 호출 전이 아니라 감지기에서 — C-8). 정상 운영엔 heartbeat 없음(C-1 확정), paused 동안만 보류 흔적.
- **entries_halted (Q7=A, critic#4로 B→A 전환)**: WakeDetector가 **`entry_inducing=True` WakeEvent를 발화하지 않는다**(detector-레벨 억제) = 상승 abnormal-move + 진입성 watch 조건. new_fill·protective_reassess·SELL성 watch는 항상 통과.
  - **B(프롬프트+gate)를 버린 이유**: gate(`gate_agent_decision`)는 entries_halted를 **안 본다**(`gate.py:8` 명시 — 사람 락만 확인). 즉 "프롬프트가 막고 gate가 최종 차단"의 **gate 안전망이 실재하지 않음** → LLM이 지시를 무시하면 BUY가 그대로 실행. 그래서 **발화 자체를 detector에서 억제**하는 A로 확정.
  - `entries_halted`는 main에 소비자가 없으므로(C-8) **소비 훅 신규** = WakeDetector가 `RunState.entries_halted`를 읽어 `entry_inducing` wake를 드롭. (스케줄 turn은 평소대로 실행 — 진입 억제는 wake 단계에서.)
  - WakeEvent의 `entry_inducing` 분류는 kind+payload로 결정(상승 abnormal-move=True, watch는 intent가 진입성이면 True). 분류는 순수함수(PBT 대상) — 오분류 시 보수적으로 True(억제 쪽) 처리(fail-closed, SECURITY-15).

---

## BLM-8 — 결정 흐름(불변 — 변경 없음 명시)

LLM turn 산출 → `decisions.jsonl` → `gate_agent_decision`(main) → RiskManager(bracket/OCO) → Broker. F3는 **이 경로에 손대지 않는다**. 신규 엔티티는 전부 입력(brief)·트리거(wake)·기록(watch) 계층이며, 주문 권한은 0이다(advisor-only, BR-1).
