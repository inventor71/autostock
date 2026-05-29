# 비즈니스 규칙 — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · Functional Design · 2026-05-29._
_F2 business-rules(BR-1..9)를 detached+file-drop로 재구현 + 신규 BR-10/11. 각 규칙은 코드/테스트로 강제._

---

## 계승 규칙 (F2 → F4, 적용 위치만 이동)

- **BR-1 확인(confirm)** — **Unit B로 이동.** 확인(`y/N`·`CONFIRM`)은 운영자 도구가 수행하고, 데몬은
  `confirmed=True`인 명령만 실행한다(`confirmed!=True`→거부, fail-closed). 파괴적 명령(`flatten_all`/`kill`)의
  `CONFIRM` 강확인도 Unit B 책임. **데몬 계약(BR-1' 신설):** 미확인 명령은 절대 실행하지 않는다.
- **BR-2 거래 실행** — 동일. 사람 거래는 `DecisionExecutor`→`RiskManager`(bracket/OCO)→`Broker` **동일 게이트**,
  `Decision.source="human"`, 크기 의미($=노셔널/sh=주식수/%=보유비율-매도전용), 무포지션 처리(BR-2.6),
  장 마감 보류 큐 드레인(BR-2.7). 사람 거래는 `decisions.jsonl`/커서 미접촉(직접 `execute_decision`, 멱등성 보존).
- **BR-3 게이팅(RunState)** — 동일. paused=예약 턴 no-op(보호·청산·사람명령 유지); entries_halted=에이전트 BUY 차단
  (사람 `/buy`는 경고 후 오버라이드); RunState ET-date 영속(BR-3.3).
- **BR-4 사람-락 상태머신** — 동일(BR-4.1..4.11). locked→PendingApproval, approve→실행+해제, reject→카운트++,
  2회→denied, 재거래→리셋(BR-4.11), 보호주문 예외(BR-4.6), unlock/자정 sweep 시 outstanding pending 해소(BR-4.10),
  불변식 단조성(BR-4.9, PBT-03).
- **BR-5 승인 노출/처리** — **알림 채널만 변경.** 콘솔 한 줄 → **`SteeringEvent(kind=pending)`** push(FR-6).
  `approve`/`reject`는 file-drop verb. 결과는 에이전트 피드백(BR-5.3).
- **BR-6 reconcile** — 동일 + C-4(트리거 유형별 run_fn). turn_lock 공유, bounded-blocking 우선권(CQ-R1=A),
  디바운스, best-effort 비중단(BR-6.3).
- **BR-7 동시성/직렬화** — 설계 취지 동일하나 **/critic #2/#3 반영해 정밀화**(코드는 재구현 신규, "계승" 아님):
  - **BR-7.1' (단일 워커 funnel):** 변이는 단일 CommandWorker. **단, `main`의 스케줄러는 `_intraday/_open_execute/_eod`에서
    `executor.execute_pending()`를 *스케줄러 스레드*에서 직접 호출(`modes/agent.py`)** → F4는 이 **스케줄러측 executor
    호출도 CommandWorker 큐로 funnel**해야 단일-워커 불변식이 성립(직접 호출 금지). `.executor_state.json` 쓰기는
    **원자적(temp+rename)** 으로(현재 `executor.py:80-84`는 비원자적 overwrite).
  - **BR-7.2' (불변식 범위):** "broker 변이+커서 단일 스레드"는 **데몬 내부**에 한함. 에이전트 서브프로세스는 자체
    `AlpacaBroker`로 **read-only account/orders**를 본다(`tools/__main__.py:21-30`) — 이는 별도 라이브 *읽기* 클라이언트라
    커서·주문에 무해(전역 단일-브로커-스레드 주장 금지). `src/agent/tools`는 read-only 유지(변이 추가 금지).
  - **BR-7.3' (turn 직렬화는 신규):** `main`에 `TurnCoordinator`/`turn_lock`/`ReconcileWorker` **부재**(F2 브랜치 전용) →
    F4가 **새로 구현**. 스케줄러는 `add_job`에 **`max_instances=1, coalesce=True` 명시**(현재 `scheduler.py:13`는 기본값
    암묵 의존). 동일 `session_id`에 `claude --resume` 2개가 겹치지 않음을 테스트로 고정.
  - 읽기는 직렬화 경로 무관(BR-7.4, 부수효과 0).
- **BR-8 에러/안전(fail-closed)** — 동일 취지. 단 BR-8.3(비-TTY 콘솔 비활성)은 **N/A**(콘솔이 in-process가 아니므로);
  대신 **운영자 도구 부재/크래시 시 데몬 정상 거래**(file-drop을 아무도 안 써도 무영향). 스레드 격리(BR-8.2),
  `cancel`의 보호 제거 경고(BR-8.4).
- **BR-9 로깅/감사** — 동일. InterventionRecord append-only(SECURITY-13), 비밀정보 0(SECURITY-03).
  BR-9.3(loguru stdout 끔)은 **N/A**(in-process 콘솔 없음) — 데몬 로그는 파일/표준 싱크 유지.

---

## F4 신규 규칙

### BR-10 권한 분리 (이번 유닛의 핵심 보안 규칙) [Q8 하드 제약, NFR-1] — **/critic #1 반영 재설계**
운영자 명령 권한은 research/intraday/PM 에이전트 세션에서 **구조적으로 접근 불가**여야 한다.
**⚠ 적대검토 #1 확인(`session.py:73-83,176,189,194`):** 에이전트는 제약 없는 `Read`를 갖고(절대경로 허용),
`cwd=workspace`지만 Read/Glob/Grep/Bash가 **절대경로**에 닿으며, `env=dict(os.environ)`로 **데몬 환경이 에이전트에
복사**된다 → **토큰을 `steering/`나 데몬 env에 두면 에이전트가 읽을 수 있다.** 따라서 "토큰을 steering/에 둔다"는
원안은 **구조적 보장이 아니다.** 재설계(방어의 *주축은 훅*, 토큰은 보조):
- **BR-10.1 (주축 — 에이전트 능력 봉쇄, MANDATORY):** `AgentSession`에 **PreToolUse 훅(필수)** 을 붙여
  `Read/Write/Edit/Glob/Grep/Bash`가 **`workspace/` 밖 경로에 닿는 것을 거부**한다(절대경로 포함). 또한
  `Bash(python -m src.agent.tools:*)` 접두 매칭이 **뒤에 `; cat …` 등 2차 명령을 못 붙이도록** exec-form/인자
  검증으로 좁힌다. 이게 위치·토큰보다 앞서는 **1차 구조적 경계**다. (F2 BR-10.3의 "가능하면"을 **필수**로 격상.)
- **BR-10.2 (토큰 — 보조, out-of-band):** 데몬은 운영자 토큰을 1개 생성하되 **파일시스템·데몬 env 어디에도 두지
  않는다.** Unit B(운영자 프로세스)에만 **대역 외**로 전달(운영자 프로세스 전용 env / stdin / 1회 표시-붙여넣기).
  데몬이 에이전트 서브프로세스를 띄울 때 **그 env에서 토큰을 제거(scrub)** 한다(`session.py:189`의 env 복사 누수 차단).
  데몬은 토큰 불일치/누락 명령을 거부(+로그, 값 비기록, SECURITY-03).
- **BR-10.3 (채널 위치 — 보조):** `steering/commands.jsonl`은 workspace 밖 → BR-10.1 훅과 결합해 에이전트의 상대·절대
  경로 쓰기를 모두 차단. (위치 단독은 불충분 — 훅이 강제.)
- **BR-10.4 (advisor-only 잔존 보장):** 위가 다 뚫려도 에이전트는 주문을 직접 못 넣는다(executor가 decisions.jsonl을
  승인 게이트로 처리). commands.jsonl에 `source="human"` 위조 주입이 유일 에스컬레이션이며 BR-10.1(+10.2/10.3)이 차단.
- **검증(테스트, 강화):** (a) 에이전트 세션에서 `workspace/` 밖 Read/Write 시도가 훅에 의해 거부됨; (b) 에이전트 env에
  토큰 부재; (c) 토큰 없는/틀린 주입 명령이 데몬에서 거부됨. (PBT/example + 훅 단위테스트.)

### BR-11 file-drop 멱등성 / 커서 [C-5 + /critic #5 반영]
- **BR-11.1 (torn-safe 읽기):** 공유 JSONL 리더는 **마지막 개행(`\n`)까지만 소비**하고, 개행으로 끝나지 않는 trailing
  청크(torn write)는 다음 폴까지 보류한다. **⚠ #5 정정:** 커서는 `read_decisions`식 **파싱-리스트 인덱스 금지**
  (`journal.py:110` `.splitlines()` + 스킵 시 `len()` 드리프트 확인됨) → **바이트 오프셋(또는 완전 물리라인 오프셋)**
  기반으로 정의. Unit B는 commands.jsonl에 **원자적 append**(O_APPEND 단일 write 또는 temp+rename).
- **BR-11.2 (재시작 멱등):** 바이트 오프셋 커서를 `steering/.commands_cursor`에 **원자적 영속**. **단, 권위 있는 멱등
  키는 `SteeringCommand.id`(#5)** — 오프셋과 dedup이 어긋나도 같은 id는 1회만 실행(재시작/부분읽기에도 중복·누락 금지).
- **BR-11.3:** outcome 이벤트는 `corr_id=cmd.id`로 **명령당 1회만** 발행(중복 금지).
- **공유 헬퍼(C-5):** 이 torn-safe 바이트오프셋 리더를 commands/decisions/agent_questions가 재사용(기존 `read_decisions`
  스킵-드리프트도 이 기회에 교정).

### BR-12 읽기/이벤트 채널 [FR-5/FR-6]
- **BR-12.1:** 데몬은 `steering/snapshot.json`을 주기적으로 게시(run_state/락/pending/positions/open_orders/fills
  커서/market_open + ts; C-3). 운영자 도구는 이를 읽어 status/positions/orders 표시 — **데몬 라운드트립 없이**.
- **BR-12.2:** 체결/결정/PendingApproval/agent_question/reconcile 결과는 `SteeringEvent`로 push(append-only).
- **BR-12.3:** 읽기는 토큰·직렬화 경로와 무관(부수효과 0). 에이전트 journal/trace는 운영자가 read-only 직접 접근.
- **BR-12.4 (snapshot 게시 — /critic #6 반영):** `main`의 `AgentTradingMode`는 positions/orders **인메모리 캐시가 없다**
  (`modes/agent.py:75,87`가 매 사이클 동기 broker 호출) → snapshot.json은 **전용 publisher 잡(자체 주기)** 이 broker를
  폴링해 게시하며, **원자적 쓰기(temp+rename)** 로 운영자의 torn JSON 읽기를 방지한다. publisher의 추가 broker 호출
  (`get_clock`/`get_account`/`get_open_orders`)을 레이트리밋 예산에 계상하고 **staleness 상한을 명시**(라이브 round-trip
  아님 — "fresh"는 publisher 주기까지).

### BR-13 응급 명령 지연 — 정직한 바운드 [/critic #8 반영]
"응급 lane"·reconcile "즉시"는 단일 워커 + 블로킹 broker 호출 앞에서 과장이다(F2 P1.2와 동일 결론).
- 진행 중인 1개 심볼의 보호/주문 사이클은 선점 불가: `_cancel_and_wait`(최대 6s, `executor.py:237`) + `submit_order`의
  `_poll_for_fill`(~5s, `alpaca_broker.py:67`) + `is_market_open` 전이 재시도(~3s, `:206`) → **worst-case ~11s+**.
- 따라서 문서·UX는 "즉시"가 아니라 **"진행 중 broker 작업 잔여(~11s) + 큐 선점"** 의 상한을 표기한다. 응급 lane은
  *대기 중* normal 작업보다 앞서되, *진행 중* HTTP 호출은 선점하지 못함을 명시.

---

## 컴플라이언스 매핑
- **SECURITY-03**: BR-9, BR-10.2(토큰 비기록). **SECURITY-11**: BR-10 전체(권한 분리 = 이번 유닛 강조) +
  스티어링/주문배치 분리(BR-2.1). **SECURITY-13**: BR-9, E7/E8/E2 pydantic 안전 역직렬화, append-only.
  **SECURITY-15**: BR-1'(미확인 거부)·BR-8·BR-11(torn-line)·fail-closed 전반. **SECURITY-10**: 신규 의존성 핀(NFR Design).
- **PBT-02(round-trip)**: E7/E8/E2 직렬화. **PBT-03(불변식)**: BR-2(size/source) · BR-4.9(락 상태머신) ·
  BR-10.2(토큰 검증) · BR-11(커서 단조). **PBT-10(보완)**: 미확인 거부·kill·paused 스킵·보호 예외·reconcile 실패
  내성·권한 거부 example 고정.

---

## 적대 검토(/critic, 격리 서브에이전트) 반영 — 2026-05-29 (모두 코드로 교차확인, 유효)
8건(HIGH 2, MED 4, LOW 2) 전부 `main` 코드와 대조해 유효 확인 후 본 FD에 반영. 정책 분기 없음(전부 엔지니어링 보강).
- **#1 [HIGH] 토큰 비구조적** → **BR-10 재설계**: 에이전트는 무제약 `Read`(절대경로)+`env=dict(os.environ)`
  복사(`session.py:189`)로 `steering/`·데몬env의 토큰을 읽을 수 있음 → **PreToolUse 훅(workspace 밖 차단)을 1차
  구조 경계로 필수화**, 토큰은 out-of-band(운영자 프로세스 전용)+에이전트 env scrub.
- **#2 [HIGH] 단일워커 불변식 범위** → **BR-7.1'/7.2'**: 스케줄러측 `execute_pending`도 워커로 funnel,
  커서 원자적 쓰기; 에이전트 서브프로세스의 독립 read-only broker 명시(전역 단일스레드 주장 철회).
- **#3 [MED] 동시성 primitive는 신규** → **BR-7.3'**: `TurnCoordinator/turn_lock` main 부재(재구현), scheduler
  `max_instances=1,coalesce=True` 명시.
- **#4 [MED] `execute_decision` 부재** → **BLM §3.2**: `_execute_one`(커서 무접촉) 공개 승격, market/off-hours 자체 판정.
- **#5 [MED] 커서 모델** → **BR-11**: 파싱-인덱스 금지, **바이트오프셋 + id-dedup 권위**, Unit B 원자적 append.
- **#6 [MED] snapshot 데이터/원자성** → **BR-12.4**: 전용 publisher 잡 + temp+rename 원자쓰기 + staleness 상한.
- **#7 [LOW] agent_questions 레이스** → **E9**: append-only 유지, 답변은 별도 `agent_answers.jsonl`(id 조인), 성장 제한.
- **#8 [LOW] "즉시" 과장** → **BR-13**: 진행 중 broker 호출 선점 불가, worst-case ~11s 바운드 표기.
- **유효성 확인(holds):** `_execute_one`(executor.py:123-160)은 커서 미접촉 — BR-2 멱등 목표는 공개 승격 시 달성 가능.
