# Intraday 루프 재설계 (F3) — 요구사항

## 1. 의도 분석 (Intent Analysis)
- **요청(User request)**: agent의 15분 intraday 루프를 재설계해 "더 나은 LLM trader"로. 5개 개선을 한 묶음으로.
- **요청 유형**: Enhancement (기존 agent intraday 루프).
- **범위**: Multiple Components — `src/agent/prompts.py`(intraday_prompt), `src/agent/orchestrator.py`(run_intraday/이벤트 turn), `src/trading/modes/agent.py`(_intraday 배선), `src/agent/review.py`(brief 조립 패턴 재사용), 신규 brief/게이트 모듈, `workspace/watch.jsonl`(신규), **main `src/agent/steering/`**(F4 재구현체: TurnCoordinator/ReconcileWorker/SteeringState/CommandBus/jsonl/gate) 재사용·확장. *(원래 F2@f63fad2 엔진 위에 설계됐으나 F4가 재구현해 main 머지 — §11.0 재정합 참조.)*
- **복잡도**: Moderate–Complex (advisor-only 유지로 직접 주문은 없음 — 그러나 agent 의사결정 입력·빈도와 동시성 모델을 바꾸므로 정합성 영향 큼).
- **요구사항 깊이**: Standard.

## 2. 배경 — 현행 문제 (오늘 trace 기준)
1. 13개 intraday turn 중 결정 산출 1개, 나머지 12개는 매번 5종목 시세를 처음부터 재수집해 같은 표를 재서술.
2. `run_intraday()`가 quotes 없이 호출 → 프롬프트 가격 줄이 항상 비어 agent가 매 틱 직접 `quote` 호출(재계산).
3. intraday에서 `account`/`news` 미사용 → META 체결을 **추론**(시세 저가가 $630 터치)으로 판단, broker 진실 미확인 → journal/broker 어긋남 위험.
4. 프롬프트의 "thesis 변화(신규 뉴스/촉매)?" 분기가 죽어 있음(intraday에 뉴스 미점검).

## 3. 설계 방향 (핵심 — Q1=X에 따른 재프레이밍)
**Python 게이트로 LLM을 스킵하지 않는다.** 대신:
- **(a) 15분 스케줄 intraday LLM turn은 그대로 유지**하되, 구조화 brief 주입으로 *판단할 게 없을 땐 cheap하게* 끝나고(프롬프트 캐시 + 불필요한 도구 호출 제거), *판단이 필요할 땐* reasoning 후 결정.
- **(b) 그 위에 이벤트 기반 wake turn 추가** — Python이 특정 wake 조건을 감지하면 다음 15분 틱을 기다리지 않고 **우선(out-of-band)** LLM turn을 발화.
- 비용은 현재 부담 수준이 아님(사용자 확인). 따라서 이 재설계의 가치는 *비용 절감(스킵)* 이 아니라 **정합성(체결 진실/뉴스 촉매) + 반응성(이벤트 즉시 발화) + 품질(재계산 제거로 판단에 집중)** 에 있다.

## 4. 잠긴 아키텍처 제약 (재설계가 따르는 것)
- **Advisor-only**: agent는 주문을 직접 넣지 않는다. `decisions.jsonl` → RiskManager → Broker가 유일한 주문 게이트.
- **Exchange resting OCO**: stop/target은 거래소 상시 대기 주문으로 기계적 자동 트리거. **LLM은 "가격이 레벨에 닿았는가" 부담을 지지 않는다.** → wake 조건은 *판단이 필요한* 이벤트로 한정(단순 닿음 제외).
- **agentic path는 backtest 비대상**(web/비결정성) — 검증은 paper/live + 단위/PBT.

## 5. 통합 제약 (CQ 답변) — *기반이 F2→F4(main 머지)로 이동, §11.0 참조*
> **2026-05-30 갱신**: 아래 CQ는 F2(human-steering-console) 위에 F3를 올린다는 전제였다. F2는 F4가 폐기·재구현했고 그 엔진이 **main에 머지**됐으므로, "F2"를 **"main의 `src/agent/steering/`(F4)"**로 읽는다. CQ-A의 "F2 initial 구현 완료" 선행조건은 **F4 머지로 이미 충족**(주문 경로·동시성 엔진이 main에 존재). 나머지 CQ의 *취지*(공유 단일 turn 엔진/snapshot 캐시/RunState 게이팅)는 그대로 유효하며 F4 API에 대응한다.
- **CQ-A=A**: F2 **initial 구현 완료 후 그 위에서** F3 *구현*. F3 *설계*(req/functional/NFR)는 선행 가능. *(→ 충족됨: main에 F4 엔진 존재)*
- **CQ-B=A**: F2 `ReconcileWorker`/`TurnCoordinator`를 **일반화해 공유** — F3 wake 트리거(체결/움직임/watch-trigger)를 트리거 소스로 추가. 단일 background-turn 엔진, turn_lock 하나, 중복 메커니즘 금지.
- **CQ-C=A**: brief의 account는 `SteeringState.snapshot()` 캐시에서 읽음(broker 직접/오프스레드 호출 금지 — F2 NFR-1 단일워커 불변식 유지).
- **CQ-D=A**: 게이트/워커는 `run_state` 확인 — paused면 LLM 발화 보류, entries_halted면 BUY 유발 wake 억제(보호/ADJUST_STOP/SELL wake는 허용).

## 6. 기능 요구사항 (Functional Requirements)

### FR-1 — 구조화 watch-trigger 저장소 (`workspace/watch.jsonl`) [Q3=A]
- agent가 append하고 Python 게이트가 읽어 평가하는 append-only JSONL.
- 필드(초안): `id`, `symbol`, `condition`(예: `close_above`/`close_below`/`price_above`/`price_below` + `level`), `intent`(예: ADJUST_STOP→제안 stop), `valid_until`(ET date), `thesis_ref`, `created_ts`.
- F2 journal 규율 준수: append-only, torn-line 가드(미완성 trailing line skip), 완전 라인만 커서 진행.

### FR-2 — intraday brief 조립 (Python) [Q4=A, Q5=A, Q6=A]
모든 intraday LLM turn(스케줄 + 이벤트 wake)에 주입할 brief를 Python이 조립:
- 종목별: 현재가 / 세션 고·저 / 거래량 페이스.
- 플랜 레벨: stop / target / entry / 등록된 watch-trigger 레벨, **각 레벨까지의 거리**.
- **account 스냅샷**: 보유/잔존 주문/체결(=체결 진실). 출처는 `SteeringState.snapshot()` 캐시(NFR-2). **⚠ C-3 참조**: 현재 snapshot은 `positions_count`+`market_open`만 담고(`agent.py:70-80`) 스케줄 turn 꼬리에서만 갱신됨 → F3가 **snapshot 페이로드 확장(positions+open_orders+fills 커서)** + **짧은 주기 bus job 갱신**을 추가해야 실제 "체결 진실"을 담는다.
- **직전 turn 대비 델타**: 무엇이 바뀌었나(신규 체결, 새 고저, 레벨 근접 변화).
- **뉴스 diff**: 직전 turn 이후 신규 헤드라인만(FR-6).
- `review.outcome_lines`의 levels-vs-price 조립 패턴 재사용 가능.

### FR-3 — 스케줄 15분 intraday turn 유지 + cheap화 [Q1=X, Q7=X]
- 15분 스케줄 turn은 **기본적으로 항상 실행**(게이트 스킵 없음). brief 덕에 nothing-to-do면 빠르게 종료, 판단 필요 시 reasoning 후 결정.
- **단, skip-if-busy [C-2 확정]:** 스케줄 발화 시점에 **다른 LLM turn(특히 out-of-band wake turn)이 아직 실행 중**이면(예: 14분에 깬 wake turn이 1분 이상 돌아 15분 슬롯과 겹침) 그 15분 스케줄 발화는 **스킵**(큐잉하지 않음) — 직전 wake turn이 이미 fresh 판단을 제공했으므로. 연달아(직전 turn이 슬롯 직전에 끝나 back-to-back) 두 번 도는 것은 허용. 즉 turn_lock을 **non-blocking으로 시도하고, 점유 중이면 스킵**. **⚠ C-1(critic) 참조**: 현재 `TurnCoordinator.scheduled_turn()`은 무조건 blocking이고 `_reconcile_waiting` 카운터가 wake turn *실행 중*에도 ≥1이라 스케줄 turn이 스킵이 아니라 **큐잉**된다(`turns.py:30-56`). → "turn in-flight" 플래그를 waiter 카운트와 **분리**하고 `try_scheduled_turn()`(점유 시 False→스킵)을 **추가**해야 함(순수 재사용 아님, F2 primitive 수정).
- F2 `_with_human_context` prepend(사람 지시/대기승인/최근개입)는 **유지**(재작성된 intraday 프롬프트가 떨어뜨리지 않을 것).

### FR-4 — 이벤트 기반 wake turn [Q1=X, Q2=A,C,D,E, CQ-B=A]
- Python이 wake 조건을 감지하면 **다음 스케줄 turn보다 우선**하는 out-of-band LLM turn을 발화.
- wake 조건:
  - **(A) 신규 체결** — 직전 turn 이후 broker 체결(진입/보호선 체결 등).
  - **(C) 비정상 움직임** — 일중 가격 이동 > 임계(예 1.5×ATR) 또는 거래량 급증.
  - **(D) watch-trigger 충족** — FR-1에 등록된 조건 충족.
  - **(E) 보호선 체결/임박에 따른 thesis 재평가** — 단순 닿음이 아니라 손절 후 재진입 등 판단 필요.
  - 제외: **B(뉴스)** 는 스케줄 turn이 brief로 읽음(FR-6) / **F(EOD 강제)** 는 기존 EOD turn이 담당.
- 메커니즘: F2 `ReconcileWorker`(디바운스 → turn_lock 우선 발화)를 일반화해 트리거 소스 추가(CQ-B).
- 프롬프트: 시장 이벤트 wake는 사람-개입용 `reconcile_prompt`가 아니라 **intraday/brief 기반 프롬프트 + 트리거 사유**로 구분.

### FR-5 — 조건부 ADJUST_STOP [Q9=A]
- watch.jsonl의 조건(예 "RTX $182 위 마감 시 tighten")을 Python이 감지 → wake turn(FR-4-D) 발화 → **LLM이** ADJUST_STOP 여부 판단·기록(advisor-only; Python은 감지만, 판단·결정은 LLM).

### FR-6 — 뉴스 diff [Q6=A]
- 직전 turn 이후 **신규 헤드라인만** brief에 주입(중복 무시; diff 감지는 Python의 가벼운 폴링). 그 자체는 wake 트리거 아님(스케줄 turn이 읽음).

### FR-7 — RunState 연동 [CQ-D=A]
- 게이트/워커는 발화 전 `run_state` 확인:
  - **paused**: LLM 발화 보류(§9 확인 항목 참조 — 보류 사실의 흔적 남김).
  - **entries_halted**: BUY를 유발하는 wake만 억제. 보호선/ADJUST_STOP/SELL wake는 허용.

## 7. 비기능 요구사항 (Non-Functional Requirements)
- **NFR-1 (turn 직렬화)**: 모든 intraday LLM 발화(스케줄 + 이벤트 wake)는 F2 `TurnCoordinator` turn_lock을 경유. bare `session.run_turn` 금지(두 `claude --resume` 겹침 방지). **스케줄 turn은 non-blocking 획득(점유 중이면 스킵, FR-3 C-2)**; wake turn은 F2 reconcile과 동일하게 다음 스케줄보다 우선. (APScheduler `max_instances=1`/coalesce는 스케줄 job의 자기-중첩만 막으므로, wake turn과의 경합 스킵은 turn_lock 레벨에서 처리.)
- **NFR-2 (broker 접근)**: account/체결 진실은 `SteeringState.snapshot()` 캐시에서 읽음. 스케줄러/워커 스레드에서 broker mutation·직접 호출 금지(F2 단일워커 불변식).
- **NFR-3 (베이스·순서)**: ~~F2 initial 구현 완료 후~~ → **main(F4 머지)에서 분기한 worktree** 위에서 F3 구현(CQ-A 충족, §11.0). F3 설계는 선행했고, 구현 베이스는 main.
- **NFR-4 (fault isolation)**: wake 감지·발화 실패가 데몬을 죽이지 않음(F2 best-effort 패턴 — 예외는 로깅 후 계속).
- **NFR-5 (보안/테스트)**: Security Baseline 적용분(SECURITY-03 로그에 비밀 금지 / -15 fail-closed). PBT Partial(Hypothesis): 게이트 조건 평가·레벨 거리 계산·watch-trigger 파싱의 순수함수 불변식 [Q12=A].
- **NFR-6 (검증)**: 전체 회귀(현행 ~196 테스트)+신규 단위/PBT 통과 후 머지. agentic path backtest 비대상.

## 8. 범위 / 빌드 단위 / 순서 [Q10=A, Q11=A]
- **단일 유닛 `intraday-redesign`**, 새 git worktree+branch에서 구현, 라이브 main은 머지 전까지 무영향.
- 내부 순서: (1) watch.jsonl 스키마 + brief 조립(account+levels+delta+news diff) → (2) Python wake 감지(체결/움직임/watch-trigger) → (3) prompts/orchestrator 주입 배선(스케줄 turn cheap화 + 이벤트 turn) → (4) cadence: 스케줄 유지 + 이벤트 우선 발화(F2 워커 일반화) → (5) 조건부 ADJUST_STOP 감지 연결 → 전체 회귀+신규 테스트.
- (no-op heartbeat는 일반 기능으로는 제외 — §9 확인 항목의 paused 경우만 예외.)

## 9. 확인 항목 — 해결됨 (2026-05-29 사용자 확정)
- **C-1 (Q8 ↔ CQ-D heartbeat) — 확정**: 정상 운영엔 heartbeat 없음(15분 LLM이 늘 실행되므로 no-op tick 자체가 없음, Q8/Q10). **`/pause` 동안에만** LLM 발화를 보류하고 그 보류 사실을 최소한으로 남긴다(FR-7).
- **C-2 (이벤트 wake ↔ 스케줄 turn 중복) — 확정**: back-to-back 중복(직전 wake가 슬롯 직전에 끝남)은 허용. **다만 14분에 깬 wake turn이 1분 이상 돌아 15분 스케줄 슬롯과 겹쳐 아직 실행 중이면, 그 15분 스케줄 발화는 스킵**(skip-if-busy, FR-3/NFR-1).

## 11.0 통합 기반 재정합 — 2026-05-30 (F4 머지 후, /ai-dlc-resume)
**전제 변경**: 이 문서가 통합 기반으로 명시한 F2 동시성 엔진은 **미머지 브랜치 @f63fad2** 였으나, F4(steering console redesign)가 그 엔진을 **재구현해 `main`에 머지**(merge `1719fcf`). 따라서 통합 surface는 이제 `feat/human-steering-console`이 아니라 **`main`의 `src/agent/steering/`**(F4 재구현체)다. F3 construction은 **main에서 분기한 worktree** 위에 올린다(F2 브랜치 아님).

**§11의 critic 발견(F2@f63fad2 대상)을 main과 재대조한 결과** — F4가 이미 흡수한 것이 많아 F3 범위가 줄었다:

| 발견 | main(F4) 상태 | F3 잔여 작업 |
|---|---|---|
| **C-1** HIGH skip-if-busy = TurnCoordinator 수정 | ✅ **이행** — `TurnCoordinator.try_scheduled_turn()`(`turns.py:37`, in-flight 플래그를 waiter 카운트와 분리, reconcile 우선=CQ-R1 포함); `modes/agent.py:70`에서 이미 사용 | 없음(그대로 사용). wake-vs-스케줄 겹침 통합테스트만 추가 |
| **C-3** HIGH snapshot 페이로드 | 🟡 **대부분 이행** — `runtime.publish_snapshot`이 positions+open_orders 포함, **5초 주기 bus job**(`modes/agent.py:181`)으로 갱신 | **fills 커서/new-fill diff**(FR-4-A wake용)만 신규 추가 |
| **C-4** MED per-kind run_fn | ✅ **이행** — `ReconcileWorker.trigger(run_fn, kind=)`, kind별 dict·단일 lock·`reconcile_turn` 봉투(`turns.py:82-114`) | wake용 신규 kind(체결/움직임/watch) 추가만 |
| **C-5** MED 공유 JSONL reader+커서 | ✅ **이행** — `jsonl.read_complete_lines`(byte-offset torn-safe)+`ByteCursor`(영속) | watch.jsonl을 그 위에 배선 + ET-date fired 커서 + `valid_until`을 `daily_sweep`에 합치기 |
| **C-6** MED 뉴스 폴링 인프라 | ❌ **미존재** | 그대로 F3 신규(FR-6) |
| **C-7** LOW 게이트 입력 분리 | 설계 노트 | 그대로 F3 wake 감지기에 반영 |
| **C-8** LOW paused/entries_halted/anchoring | 🟡 **부분** — `RunState`+`_paused()`가 스케줄 경로에 배선(`modes/agent.py:55-56,106`); `gate.gate_agent_decision`은 lock 게이팅 담당 | **`entries_halted` 소비자 없음**(신규 훅) + **wake 경로의 paused-보류/보류 로그**(신규) + IntervalTrigger 비정렬(불변) |

→ **순수 F3 신규 작업(불변)**: 구조화 intraday brief(`run_intraday`는 여전히 quotes 미전달, `orchestrator.py:113`) · 이벤트 wake 소스(new-fill/abnormal-move/watch-trigger) · 뉴스 diff · watch.jsonl 스키마. 아래 §11 원문은 *F2@f63fad2 시점의 진단*으로 보존하되, 실제 구현은 위 표의 "main 상태"를 기준으로 한다.

## 11. 적대 검토(/critic) 반영 — 2026-05-29 (당시 F2@f63fad2 대상; 현행 판정은 §11.0 표 참조)
격리된 `critic` 서브에이전트가 이 문서의 단정을 실제 F2 코드(worktree @ f63fad2)와 대조해 7건을 지적. 메인 세션이 각 건을 `path:line`으로 재확인했고, 전부 엔지니어링 보강으로 반영(정책 분기 없음). 이 항목들은 Functional/NFR Design에서 *반드시* 반영할 설계 제약이다. **(2026-05-30 주의: C-1/C-4/C-5는 F4가 main에 이미 구현 — §11.0 참조. 아래 원문은 진단 이력으로 보존.)**

- **C-1 [HIGH] skip-if-busy는 TurnCoordinator 수정이다 (순수 재사용 아님).** `scheduled_turn()`은 blocking(`turns.py:39`), 호출부도 yield 값 무시(`orchestrator.py:100`). `_reconcile_waiting`은 wake/reconcile turn이 *실행되는 동안에도* ≥1(`turns.py:45-56`)이라, 현 코드로는 스케줄 turn이 wake turn 뒤에 **큐잉**된다 — C-2의 "스킵"과 정반대. **수정 필요**: "turn in-flight" 플래그를 waiter 카운트와 분리 + `try_scheduled_turn()`(점유 시 스킵). 또한 F2의 reconcile-priority(대기 중 reconcile에 스케줄이 *yield*)와 C-2(실행 중 turn 있으면 *skip*)를 구분해 명세. (FR-3/NFR-1 갱신됨.) **확인용 통합테스트**: "15분 슬롯에 wake turn 실행 중 → 스케줄 스킵(큐잉 아님)".
- **C-3 [HIGH] snapshot 캐시에 체결/주문/포지션이 없다.** `update_snapshot`은 `positions_count`+`market_open`만 저장(`agent.py:70-80`), 갱신은 스케줄 turn 꼬리(`_open_execute`:119, `_intraday`:133)뿐. → (1) brief의 "account 진실"이 카운트만 → LLM이 결국 `account`를 또 호출(재계산 부활). (2) "신규 체결 wake"가 스케줄 turn 이후에야 카운트 변화로만 감지 → out-of-band 의미 상실. **수정 필요(FR-2/FR-4-A)**: snapshot 페이로드를 positions+open_orders+fills 커서로 확장하고 **짧은 주기 CommandBus job**으로 갱신; 신규 체결은 broker fills/positions diff로 감지(가격 추론·카운트만으로 아님). NFR-2 준수(broker 접근은 bus 경유).
- **C-4 [MED] ReconcileWorker는 단일 `run_fn`/단일 debounce/비재진입 Lock.** `run_reconcile(acquire=False)`는 `reconcile_prompt`에 고정(`orchestrator.py:153`)이고 `ReconcileWorker._fire`가 `reconcile_turn()` 안에서 lock 보유(`turns.py:81-83`); `_run_fn`·`_timer` 각 1개(`turns.py:62,64`), 트리거 소스 1개(console). → 시장-이벤트 wake를 그대로 끼우면 (a) 비재진입 `threading.Lock` 이중 획득 데드락 위험, (b) 사람 reconcile와 시장 wake가 debounce로 **합쳐져** 마지막 `run_fn`/프롬프트만 실행(의도 손실). **수정 필요(FR-4/CQ-B)**: 트리거 *유형별* run_fn/프롬프트(또는 typed-event 큐를 1 turn으로 drain하며 프롬프트 선택), lock 1개·유형별 debounce, 모든 발화는 단일 `reconcile_turn()`/`acquire=False` 봉투 안에서.
- **C-5 [MED] watch.jsonl의 "torn-line/append 규율"은 아직 재사용 가능한 형태가 아니다.** 가드는 `read_decisions` 내부 전용(`journal.py:117-138`), 공유 헬퍼·커서 없음(매 호출 전체 재파싱). 게다가 writer=agent **subprocess**, reader=daemon → 진짜 교차-프로세스 append/read. **수정 필요(FR-1/FR-5)**: 공유 "완전 JSONL 라인 읽기" 헬퍼 추출 + **fired/seen 커서를 ET-date 스코프로 영속**(재시작 후 재발화 금지) + `valid_until` 만료를 ET-자정 sweep(`sweep_expired`)에 합치기.
- **C-6 [MED] 뉴스 폴링 인프라 없음.** `news()`는 per-symbol `yf.Ticker().news` 블로킹 + 15분 캐시(`market.py:154`, `news_provider.py:35`). → 데몬 스레드에서 N종목 폴링 시 블로킹/레이트리밋; 15분 캐시가 diff 입도를 사실상 15분으로 제한. **반영(FR-6)**: 별도 스레드(또는 bus)에서, 캐시 TTL≥15분 주기로, per-symbol 마지막 헤드라인 키 영속, 보유/감시 종목만. (wake 트리거 아님이므로 지연 비치명적 — 설계상 OK.)
- **C-7 [LOW] advisor-only 경계는 시장데이터엔 OK, 체결만 bus 필수.** 게이트의 quote/indicators/abnormal-move는 데몬의 `data_provider`로 계산 가능(NFR-2 위반 아님). 단 account/fill 입력만 bus-snapshot 경유. **반영(NFR-2)**: 게이트 입력을 명시적으로 분리(시장데이터=데몬 직접, account/fill=bus snapshot).
- **C-8 [LOW] paused 단락 위치 + entries_halted 미참조 + interval anchoring.** `_intraday`는 paused면 orchestrator 호출 *전에* early-return(`agent.py:122-128`)이라 보류 로그를 담을 turn이 없음 → **보류 로그는 wake 감지기/워커가 담당**(BUY vs 보호 구분도 거기서). `entries_halted`는 `_intraday`에서 미참조 → FR-7 BUY-wake 억제는 신규 훅. `add_batch_job`은 시작 기준 IntervalTrigger(`scheduler.py:27-30`, 벽시계 15분 정렬 아님) → C-2의 "슬롯 겹침"은 근사. wake turn과 다음 스케줄 turn은 **같은 day session id 공유**(의도된 동작 — wake 추론이 다음 스케줄에 보임)임을 명시.

## 10. 요약
재설계의 본질은 "15분 LLM을 스킵"이 아니라 **(1) 구조화 brief 주입으로 매 스케줄 turn을 재계산 없이 cheap·정확하게 만들고(account 진실/뉴스 diff/델타), (2) 판단이 필요한 시장 이벤트(체결/비정상 움직임/watch-trigger/보호선 재평가)에서 F2의 background-turn 엔진을 일반화해 우선 발화**하는 것. 모든 LLM 발화는 F2 turn_lock·snapshot 캐시·RunState를 존중하며, F2 initial 구현 위에 단일 유닛으로 worktree에서 구축한다.
