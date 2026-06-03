# NFR 설계 패턴 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · NFR Design · 2026-05-29._
_입력: `../nfr-requirements/` + `../functional-design/`. 내부 엔지니어링 결정(사용자 UX 분기 없음)._

이 기능의 핵심 위험은 **돌아가는 데몬에 동시성을 더하는 것**이다. 아래 패턴이 NFR-1(직렬화)을 실현한다.

---

## P1. 동시성/직렬화 — "단일 브로커-접근 스레드" + "turn-lock 분리" (핵심)

### P1.1 두 개의 독립된 직렬화 축
- **EngineSerialization = 단일 CommandWorker 스레드**: **브로커 *변이*(주문 제출/취소)와 executor 커서**를 만지는
  연산은 오직 이 한 스레드에서만 실행된다(콘솔 변이·승인 실행·`/cancel`·`/stop`·스케줄러의 executor 단계·폴드 청산).
  → 브로커 주문 동시호출·커서 read-modify-write 레이스가 이 한 스레드 내에선 **구조적으로 불가능**.
- **불변식 정밀화(검토 #1/#7/#8 반영):**
  - "레이스 불가능"은 **데몬 프로세스 내부의 브로커 *변이* + executor 커서**에 한함(전역 단일-브로커-스레드 주장 아님).
    **읽기 전용** 호출(`is_market_open`/clock, 시세)은 부수효과·커서 영향이 없어 다른 스레드에서 호출돼도 안전하나,
    네트워크 절감을 위해 가능하면 **캐시 스냅샷**(CommandWorker가 갱신)으로 대체.
  - **에이전트 서브프로세스의 독립 브로커(검토 #1):** `claude`는 별도 OS 프로세스로 `python -m src.agent.tools account`
    (`tools/__main__.py:21-30`가 자체 `AlpacaBroker` 생성, `market.account` → `get_portfolio_state`/`get_open_orders`)를
    호출할 수 있다(session.py:73-83가 허용). 즉 데몬 캐시와 **무관한 라이브 읽기 클라이언트**가 하나 더 있다 →
    에이전트의 장부 인식은 CommandWorker 캐시와 일시 불일치할 수 있다(읽기뿐이라 커서/주문 안전). **계약:**
    `src/agent/tools`는 read-only 유지(변이 추가 금지). 전역 "단일 브로커 스레드" 표현은 쓰지 않는다.
  - `decisions.jsonl`은 **두 축이 공유**한다(turn 축의 `claude` 서브프로세스가 append, CommandWorker가 read).
    브로커·커서는 단일 스레드라 안전하지만 이 파일은 cross-axis다 → **torn(부분 기록) 마지막 줄** 처리 필요(P2 멱등성 참조).
- **TurnLock = LLM 세션 직렬화**: `AgentSession`(`claude --resume`) 호출은 `turn_lock`(threading.Lock)으로 직렬화.
  보유자: 예약 턴(research/intraday/eod) **및** reconcile 턴. → 동일 세션 동시 `--resume` 충돌 방지.

### P1.2 왜 둘을 분리하나 + 응급 명령의 실제 지연 바운드 (검토 #1 반영)
- LLM 턴(수 분 가능)은 하위 프로세스가 **저널만** 쓰고 브로커를 안 만진다 → **turn_lock만 보유, Engine은 비점유**.
  따라서 긴 research 턴은 응급 명령을 막지 않는다(turn 축 대비로는 "즉시"가 참).
- **단, FIFO 단일 워커이므로 응급 명령은 *브로커 작업* 뒤에서 대기할 수 있다(이전 문서의 "즉시"는 과장):**
  - `_cancel_and_wait`(executor.py:237)는 심볼당 최대 ~6초 블로킹 폴링; 다심볼 `run_risk_exits`/`execute_pending`은 수십 초.
  - RTH 동안 스케줄러 executor 단계가 상시 enqueue됨 → 순수 FIFO면 `/kill`이 그 뒤에 붙음.
- **보강 설계 — 우선순위 레인 + worst-case 바운드:**
  - CommandQueue를 **2-레인(emergency / normal)** 또는 PriorityQueue로 한다. 응급 명령(`/kill`·`/flatten all`·`/flatten`·
    `/pause`·`/halt-entries`)은 **대기 중 normal 작업보다 앞서** 처리된다.
  - 다심볼 executor 단계(스케줄러 발)는 **심볼 사이마다 emergency 레인을 점검**하고 비어있지 않으면 양보(yield)하여
    응급 명령을 먼저 처리한 뒤 재개한다.
  - **정직한 보장(검토 #3 정정):** 양보 단위는 **심볼 1개 단위**이고, 진행 중인 단일 심볼 연산은 선점 불가하다.
    그 연산의 실제 블로킹 상한은 ~6s가 아니라 **~11s+**: `_place_protection`는 `_cancel_and_wait`(최대 6s, executor.py:237)
    **+** `submit_order`(`_poll_for_fill` 최대 ~5s, alpaca_broker.py:79-100)이며, `is_market_open`도 전이 오류 시 ~2s 더 든다
    (alpaca_broker.py:206-221). 따라서 worst-case 응급 지연 = **진행 중인 1개 심볼의 보호/주문 사이클(~11s) + 큐 선점**.
    "전체 배치 완료까지 대기"는 아니지만 "~6s"는 과소 — `_poll_for_fill`/cancel 폴링을 줄이거나(타임아웃 하향) 응급 시
    in-flight를 중단할 수단이 없으면 이 상한을 명시적으로 수용한다.
- 예약 잡의 순서: `turn_lock 획득 → LLM 턴 → 해제` 후 executor 단계는 **CommandWorker normal 레인에 enqueue**.

### P1.5 ET-date 만료 / 자정 롤오버 (검토 #2 반영)
- **문제:** 데몬은 재시작 없이 며칠 돈다(`session.py:119` `session_date`가 매번 live ET date 계산). "로드 시 날짜≠오늘이면
  무시"만 두면 인메모리에 든 어제의 lock/denied/pending이 다음 거래일로 그대로 넘어간다("다음 거래일 자동 해제"가 재시작 의존).
- **보강:** ET-date 스코프 상태는 **(a) 접근마다 lazy 만료**(읽을 때 `entry.date != today_ET`면 제외/폐기) **+ (b) ET 자정
  롤오버 sweep 잡**(스케줄러에 1일 1회, locks/pending/directive의 만료분 정리 + 영속 파일 재기록)을 함께 둔다.
  같은 날 재시작 시 복원은 그대로(영속 파일).

### P1.3 명령 흐름
```
ConsoleThread(prompt_toolkit) ─ parse/confirm ─ enqueue(Command) ─ await(result future)
                                                      │
CommandQueue(FIFO) ───────────────────────────────> CommandWorker(단일 스레드)
   ▲ 스케줄러 executor 단계도 여기로 enqueue           └ 브로커/executor/커서/락스토어 변이 (직렬)
ReconcileWorker ── turn_lock ── orchestrator.run_reconcile()   (브로커 안 만짐)
예약 LLM 턴 ─────── turn_lock ── session.run_turn()            (executor 단계는 큐로)
```

### P1.4 SteeringState 동시 접근
- 인메모리 상태(RunState/HumanLock/PendingApproval 캐시/Directive)는 여러 스레드가 읽고(툴바·executor 게이팅) CommandWorker가 쓴다.
  → 빠른 `state_lock`(threading.Lock)으로 O(1) dict 연산 보호. 영속 파일 쓰기도 이 락 안에서.
- 하단 툴바/`/status`의 보유 수 등 브로커 값은 **CommandWorker가 사이클마다 갱신해 둔 캐시 스냅샷**을 읽음(렌더마다 블로킹 브로커 호출 안 함).

## P2. 회복성(Resilience) 패턴
- **벌크헤드/스레드 격리**: ConsoleThread·CommandWorker·ReconcileWorker·스케줄러 스레드 분리. 각 스레드는 최상위
  try/except로 감싸 예외를 잡아 로그만 남기고 **데몬을 죽이지 않음**(BR-8.2, SECURITY-15).
- **Fail-closed**: 파싱/확인 실패·미확인·타임아웃 → no-op. CommandWorker의 명령 에러 → `ExecutionOutcome(error)` 로깅, 큐 계속.
- **Best-effort reconcile + 스케줄러 직렬화(검토 #4·#5)**: try/except + **디바운스/coalesce**(짧은 시간 다수 개입을 1회로).
  - **스케줄러 설정 명시화(#4):** 현재 `TradingScheduler`는 `BackgroundScheduler()`만(scheduler.py:13) — `max_instances`/`coalesce`
    미설정이라 APScheduler 기본값(`max_instances=1`, `coalesce=True`)에 *암묵* 의존. 코드젠에서 **명시적으로 `max_instances=1,
    coalesce=True`** 설정 + 의존성 문서화(미래 변경이 직렬화 가정을 조용히 깨지 않게).
  - **reconcile 즉시성(#4 — 확정 CQ-R1=A):** reconcile는 **bounded blocking acquire**로 turn_lock을 잡되 **다음 예약 턴보다
    우선권**(진행 중 턴이 끝나면 바로 실행). max-staleness = 진행 중 턴의 잔여 시간 → FR-6 "즉시"에 최대 근접, 동시 세션 충돌 없음.
    (순수 무한 양보는 기아 위험으로 기각.)
  - 예약 턴이 경합으로 스킵될 경우 **명시적 경고 로그**(조용한 유실 금지). 실패는 로그만(데몬 비중단).
- **멱등성(검토 #4/#8)**: 사람 거래는 **직접 실행 경로**(`execute_decision`)로 RiskManager→Broker를 한 번 통과하고
  `human_directives.jsonl`에만 기록 — `decisions.jsonl`/커서는 **건드리지 않음**(에이전트 전용 유지, 기존 멱등성 보존).
  에이전트는 reconcile + 라이브 보유로 사람 거래를 인지. 실제 P&L은 브로커 trade-ledger가 출처.
  - **게이팅 parking 멱등화(#4):** 에이전트 결정의 PendingApproval 생성은 **decision 지문(symbol+action+levels+ts)** 키로
    멱등 — `execute_pending`이 배치 중간 예외로 재실행돼도 같은 결정에 PendingApproval이 **중복 생성되지 않음**.
    추가로 커서를 **결정 단위로 점진 저장**(배치 끝 1회 → 각 처리 후 저장)하여 재처리 창을 축소.
  - **torn line 방어(#8 — *현재 코드엔 없음, 코드젠에서 추가*):** 지금 `read_decisions`는 `splitlines()`라 torn/완전 줄을
    동일 처리하고(journal.py:110) 미파싱 줄은 skip+영구 누락, 커서는 `len(parsed)`(executor.py:120). 코드젠 Step 2에서:
    (a) **개행으로 끝나지 않는 마지막 청크를 파싱 전에 제거**, (b) 커서를 **완전한 *물리적* 줄 수** 기준으로 정의
    (parsed-and-filtered 리스트 길이 아님 → 기존 skip 유발 커서 드리프트도 제거). 즉 이 방어는 "설계 의도"이며 아직 미구현임을 명시.
- **자원 정리**: 모든 락은 `finally`/컨텍스트매니저로 해제. `_cancel_and_wait`(기존) 재사용.

## P3. 성능 패턴
- 읽기/쓰기 모두 **단일 CommandWorker**가 브로커 접근(동시 API 호출 0). 단일 운영자·저빈도라 처리량 이슈 없음.
- ConsoleThread는 절대 브로커/LLM에서 블로킹하지 않음 — enqueue 후 future await(작업 중 표시 가능), 결과는 patch_stdout로 렌더.
- 툴바는 캐시 스냅샷 읽기(블로킹 없음). reconcile는 async(콘솔 비블로킹, Q7=A).

## P4. 보안 패턴 (강제)
- **SECURITY-11(보안 설계)**: 스티어링 로직(콘솔/파서/상태)과 **주문 배치(executor/RiskManager) 분리** — 신규 주문 경로 없음.
  방어심층 = 사람 의도 + RiskManager 게이트 + 확인 + **사람-락 승인 게이트**. 오남용 케이스: `/flatten all`·`/kill` CONFIRM.
- **SECURITY-03**: `InterventionLog`/콘솔 출력에 비밀정보 0(redaction). 종목/수량/가격/사용자 텍스트만.
- **SECURITY-13**: 모든 영속 스토어(locks/pending/directives/intervention)는 **pydantic 안전 역직렬화**; InterventionLog는
  append-only(감사 가능: 누가=사람, 무엇, 언제, 결과).
- **SECURITY-15**: P2의 fail-closed/스레드 격리/finally 해제.
- **SECURITY-10**: `prompt_toolkit`·`rich`를 `pyproject.toml`에 고정 버전으로 추가.

## P5. prompt_toolkit 통합 패턴
- `PromptSession`을 **ConsoleThread**에서 실행(자체 asyncio 루프). 백그라운드 출력은 `patch_stdout()`로 — 입력 줄 보존(CQ2 알림 핵심).
- `bottom_toolbar` 콜러블이 `SteeringState`(run-state·승인대기·보유 캐시)를 읽어 라이브 표시.
- `Completer`: 슬래시 명령 + 보유/유니버스 심볼 자동완성. `FileHistory`로 명령 히스토리.
- **메인 스레드 역할**: 데몬 메인 스레드가 TTY면 콘솔 루프를, 아니면 기존 `while True: sleep`(헤드리스)를 돈다.
  콘솔 `quit`/Ctrl-D → 콘솔만 종료하고 메인 스레드는 sleep-wait로 전환(데몬 계속). Ctrl-C → 스케줄러 정지 후 종료(기존 동작).
- 비-TTY 감지 시 콘솔 비활성화 + 로그 한 줄(BR-8.3). loguru stdout 싱크는 콘솔 부착 시 제거(Q3=A).

---

## P6. 확인 일관성 & 구현 검증 항목 (검토 #6/#11)
- **확인 에코 TOCTOU(#6):** 강확인 시 보여주는 수치("5 포지션·8 주문")는 **확인 시점 스냅샷의 추정치**다. 실제 실행은
  FIFO로 지연될 수 있어 그 사이 체결/리스크 청산으로 장부가 바뀔 수 있다. **계약 정정:** `/flatten all`·`/kill`의 의미는
  "**실행 시점에 존재하는 것**을 청산"이며, executor가 **실행 직전 라이브 재조회**한다(안전사고 아님). 확인 프롬프트는 추정치임을
  명시하고, **결과 줄에 실제 청산/취소 수치**를 표시한다("확인한 것 = 실행된 것"을 결과로 확정).
- **구현 검증 항목(#11):** prompt_toolkit `patch_stdout`/`run_in_terminal`로 비동기 승인 알림이 끼어들 때,
  **동기 확인(`[y/N]`/`CONFIRM`) 입력 중인 버퍼가 보존**되는지 코드 생성 단계에서 실제 검증(prompt_toolkit 동작 의존).

## 패턴 ↔ NFR/규칙 추적
| 패턴 | 충족 NFR/규칙 |
|---|---|
| P1 단일 CommandWorker + turn_lock 분리 + 우선순위 레인 + 정밀 불변식 | NFR-1(직렬화), BR-7, 응급 명령 바운드(#1), #7/#8 |
| P1.5 lazy 만료 + ET 자정 sweep | 락/pending 일관성(#2) |
| P2 격리·fail-closed·best-effort(turn_lock 양보)·멱등 parking·torn-line | NFR 신뢰성, BR-6.3/BR-8, SECURITY-15, #4/#5/#8 |
| P3 비블로킹 콘솔·캐시 툴바 | NFR 성능/사용성 |
| P4 분리·redaction·안전직렬화·append-only | SECURITY-03/10/11/13/15 |
| P5 prompt_toolkit/patch_stdout/toolbar | UX(CQ-NFR1=B), BR-8.3 |
| P6 확인 TOCTOU 정정·구현 검증 | 확인 계약(#6), prompt_toolkit 검증(#11) |
