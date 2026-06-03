# Functional Design 계획 + 명확화 질문 — Intraday 루프 재설계 (F3)

> **베이스 재정합 (2026-05-30, /ai-dlc-resume)**: F4가 동시성 엔진을 재구현해 **`main`에 머지**(`1719fcf`). F3는
> **main에서 분기한 worktree** 위에 올린다. 이미 main에 있는 것: `TurnCoordinator.try_scheduled_turn`(skip-if-busy, C-1),
> `ReconcileWorker.trigger(kind=)`(per-kind, C-4), `jsonl.read_complete_lines`+`ByteCursor`(C-5), `runtime.publish_snapshot`
> (positions+open_orders, 5초 bus job, C-3 대부분). **F3 신규 잔여**: 구조화 brief 조립 · new-fill 감지(snapshot fills 커서) ·
> abnormal-move 감지 · watch.jsonl 스키마/리더 · 뉴스 diff · `entries_halted` 훅. 상세 = requirements §11.0.

이 문서는 (1) Functional Design 산출 계획(체크박스)과 (2) FD 품질을 좌우하는 **열린 설계 결정**에 대한 질문을 함께 담는다.
각 `[Answer]:` 뒤에 선택지 문자(예 `A`)를 적어주세요. 복수 선택 가능 문항은 표시해 두었고, 맞는 보기가 없으면 `X) 기타`에 설명을 적어주세요.

---

## Part A — Functional Design 산출 계획 (체크박스)

설계는 코드가 아니라 문서다(기술-비종속). 질문 답변 후 아래를 생성한다.

- [x] `construction/intraday-redesign/functional-design/domain-entities.md`
  - [x] **WatchTrigger** (E1): id/symbol/condition/level/intent/valid_until(ET)/thesis_ref/created_ts/fired(seen) 커서 모델
  - [x] **IntradayBrief** (E2): 종목별 가격/세션 고저/거래량 페이스, 플랜 레벨+거리, account 스냅샷, 직전-turn 델타, 뉴스 diff (transient)
  - [x] **WakeEvent** (E3): kind(new_fill/abnormal_move/watch_trigger/protective_reassess) + payload + 사유 텍스트
  - [x] **FillDelta / SnapshotDelta** (E4): 직전 snapshot 대비 신규 체결·포지션·주문 변화 (new-fill 감지 입력)
  - [x] main 재사용 엔티티 매핑: `RunState`/`SteeringState`/snapshot payload/`ByteCursor` (신규 아님 — 경계 명시)
- [x] `construction/intraday-redesign/functional-design/business-logic-model.md`
  - [x] **BLM-1 brief 조립** 파이프라인(입력원: 시장데이터=데몬 직접, account/fill=snapshot 캐시 — C-7)
  - [x] **BLM-2 wake 감지** 루프(주기/입력/트리거 생성) + `ReconcileWorker.trigger(kind=)` 연동(우선 발화)
  - [x] **BLM-3 스케줄 turn cheap화**: `try_scheduled_turn`로 skip-if-busy, brief 주입, `_with_human_context` 유지
  - [x] **BLM-4 watch.jsonl 수명주기**: 등록(누가 write) → 평가 → 발화 → fired 커서 → `valid_until` 만료(daily_sweep)
  - [x] **BLM-5 뉴스 diff** 폴링(스레드/주기/dedup) + brief 주입(트리거 아님)
  - [x] **BLM-6 snapshot fills 커서 확장**(C-3 잔여): publisher가 fills/positions diff를 담는 경로
  - [x] **BLM-7 RunState 게이팅**: paused→wake 보류+보류 로그, entries_halted→**[Q7=B]** wake 발화 유지+프롬프트 "진입 금지" 주입(억제 안 함; 최종 차단=`gate_agent_decision`) — 신규 소비 훅
- [x] `construction/intraday-redesign/functional-design/business-rules.md`
  - [x] BR 모음: 우선순위(wake>스케줄), skip-if-busy 의미, advisor-only 불변(주문 직접 없음), torn-line/커서 규율,
        fault isolation(감지 실패가 데몬 비중단), 보호/ADJUST_STOP/SELL wake는 entries_halted 예외, PBT 불변식 대상
- [x] (UI 없음 → frontend-components.md 생략)
- [x] 답변 검토 → 모호하면 clarification 파일 추가 → 산출물 확정 → FD 완료 메시지(2-옵션 게이트)

---

## Part B — 명확화 질문 (FD 품질 결정 항목)

### Question 1 — watch.jsonl 을 *누가 어떻게* 기록하나 (FR-1/FR-5)
구조화 watch-trigger("RTX $182 위 마감 시 tighten")를 agent가 등록해야 Python이 감지·발화한다. agent(=`claude` 서브프로세스)가 이걸 남기는 경로는?

- A) **신규 저널링 도구** `watch set/clear`(agent tools에 추가). agent가 결정과 별개로 명시적 watch 등록; Python은 `workspace/watch.jsonl`을 리더로 소비. (가장 명시적·검증 쉬움)
- B) **결정에 인라인**: agent가 `decisions.jsonl`의 ADJUST_STOP/HOLD 결정에 `watch` 필드를 실어 보내고 Python이 추출해 watch.jsonl로 투영. (도구 추가 없음, 결정과 결합)
- C) agent가 `watch.jsonl`을 **직접 파일 쓰기**. (단순하나 advisor-only 경계/검증 면에서 비선호)
- X) 기타

[Answer]: A

### Question 2 — watch 조건 어휘 (v1 범위) (FR-1)
v1에서 지원할 조건 종류는? (복수 선택 가능, 쉼표)

- A) `price_above` / `price_below` (현재가 기준 즉시)
- B) `close_above` / `close_below` (세션/바 마감 기준 — "위 마감 시")
- C) `vwap_cross` (VWAP 상·하향 돌파)
- D) `volume_spike` (거래량 급증 배수)
- E) `time_at` (특정 ET 시각 도달)
- 권장 최소셋: **A+B** (나머지는 후속). 동의하면 `A,B`.

[Answer]: A, B

### Question 3 — 신규 체결(new-fill) 감지 기준 (C-3 잔여, FR-4-A)
"직전 turn 이후 체결" wake의 감지 입력은? snapshot에 무엇을 더 담을지 결정한다.

- A) **broker 체결/활동 내역(fills/activities) 커서** — Alpaca의 체결 이벤트를 bus job이 읽어 커서 전진(가장 정확: 부분체결·보호선 체결 구분). broker 포트에 `get_fills(since)` 추가.
- B) **positions 수량 diff** — snapshot의 종목별 qty 변화로 추론(도구 추가 없음, 부분체결·동일수량 교차 못 잡음).
- C) **open_orders 소멸 diff** — 대기 주문이 사라지면 체결로 간주(보호선 OCO 체결 감지에 유리, 진입 체결엔 약함).
- 권장: **A**(진실성 최우선, NFR-2: 접근은 bus 경유). 비용/복잡도 우려면 B로 시작.
- X) 기타

[Answer]: A

### Question 4 — abnormal-move 트리거 정의 + 임계 + 설정 위치 (FR-4-C)
"비정상 일중 움직임" wake의 판정 기준은?

- A) **ATR 배수**: 일중 |가격이동| > `k × ATR(14)` (예 k=1.5). + 거래량 급증 `vol > m × 평균`(예 m=3). 둘 중 하나 충족 시 발화.
- B) **단순 % 이동**: 직전 turn 대비 |%변화| > `p%`(예 1.5%). (ATR 계산 불필요, 종목 변동성 차이 미반영)
- C) **레벨 근접**: stop/target까지 거리가 임계 이내로 좁혀짐(닿음 아님 — 판단 임박). 
- 설정 위치: **(i)** `config/settings.yaml` 신규 `intraday:` 블록 / **(ii)** 코드 상수(리터럴 기본값). 선택지 문자 뒤에 `(i)`/`(ii)` 병기.
- 권장: **A (i)** (변동성 정규화 + 외부 튜닝 가능). 

[Answer]: A (i)

### Question 5 — 동시 다발 트리거의 합치기(coalesce) 정책 (FR-4, NFR-1)
debounce 창 안에서 서로 다른 wake(예: 체결 + watch-trigger)가 동시에 발생하면?

- A) **하나의 wake turn으로 합쳐** 모든 typed-event를 한 프롬프트에 나열(사유 다중) — turn 1회, LLM이 한 번에 판단. (비용·일관성 우위; main `ReconcileWorker`가 kind별 dict라 약간 확장 필요)
- B) **kind별 개별 turn** 순차 발화(각 사유 분리, 더 많은 turn). 
- 권장: **A** (skip-if-busy/turn_lock과도 자연스럽고 재계산 최소).

[Answer]: A

### Question 6 — intraday brief 렌더링 형식 (FR-2)
brief를 프롬프트에 어떤 형태로 주입할까? (재계산 제거가 목적)

- A) **컴팩트 구조화 텍스트 블록** (종목별 1~2줄: `SYM px=… sess H/L=… vol=… | stop=… (-1.2%) tgt=… (+3.4%) watch=…`), `review.outcome_lines` 패턴 재사용. 사람·LLM 모두 읽기 쉬움.
- B) **JSON 블록** (기계적·정확, 토큰 많고 가독성 낮음).
- C) A(요약) + 접근 시 상세(레벨 근접 종목만 확장).
- 권장: **A** (또는 C). 

[Answer]: A

### Question 7 — `entries_halted` 시 억제할 "BUY-유발 wake" 정의 (FR-7, C-8)
`entries_halted`면 신규 진입을 부르는 wake만 억제하고 보호/조정/청산 wake는 허용한다. 무엇을 "BUY-유발"로 볼까?

- A) **abnormal-move(상승 모멘텀) + watch의 진입성 조건**만 억제. new-fill·protective-reassess·SELL성 watch는 항상 허용. (보수적·안전)
- B) `entries_halted` 동안 **모든 wake 발화는 유지하되, 프롬프트에 "신규 진입 금지" 지시를 주입**해 LLM이 BUY를 내지 않게(게이트는 main `gate_agent_decision`이 최종 차단). 
- 권장: **B** (감지·발화는 단순 유지, 억제는 프롬프트+기존 게이트로 — wake 분류 오류 위험 회피). A는 발화 자체를 줄여 비용↓이나 분류 필요.

[Answer]: B

### Question 8 — 뉴스 diff 범위·주기 (FR-6, C-6)
뉴스 diff는 wake 트리거가 아니라 스케줄 turn의 brief에만 들어간다(지연 비치명적).

- A) **보유 종목만**, TTL ≥ 15분 주기 폴링, per-symbol 마지막 헤드라인 키 영속(중복 제거).
- B) **보유 + watch 등록 종목**, 동일 주기.
- 권장: **B** (감시 중인 종목의 촉매도 보는 게 thesis 재평가에 유용). 부하 우려면 A.

[Answer]: B

---

## 참고 — 변경하지 않는 것 (재확인)
- advisor-only: agent는 주문 직접 안 넣음. `decisions.jsonl`→RiskManager→Broker 가 유일 게이트(불변).
- 모든 LLM 발화는 main `TurnCoordinator` turn_lock 경유(`try_scheduled_turn`/`reconcile_turn`). bare `session.run_turn` 금지.
- broker 접근(account/fill)은 bus·snapshot 경유(NFR-2). 시장데이터(quote/indicators)는 데몬 `data_provider` 직접(C-7).
- 새 동시성 프리미티브 만들지 않음 — main(F4) 것을 일반화·확장만.
