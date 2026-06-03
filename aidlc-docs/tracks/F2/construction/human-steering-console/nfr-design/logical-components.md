# 논리 컴포넌트 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · NFR Design · 2026-05-29._

기능 설계의 도메인 개념을 실행 스레드/락/컴포넌트로 매핑한다. (기술 비종속 논리 수준; 실제 모듈 경로는 Code-Gen 계획에서.)

---

## 컴포넌트 목록

### LC1. SteeringConsole (ConsoleThread)
- **책임**: prompt_toolkit `PromptSession` 실행, 슬래시 명령 파싱·확인 흐름, 결과/알림 렌더(rich + patch_stdout),
  하단 툴바·자동완성·히스토리.
- **스레드**: 데몬 메인 스레드(TTY일 때). 비-TTY면 비활성.
- **상호작용**: 변이 명령 → `CommandBus`에 enqueue 후 결과 future await. 읽기 명령 → `CommandBus`(조회)로.
  `SteeringState` 읽기(툴바). `Notifier`로부터 async 알림 수신.
- **부수효과 없음(자체)**: 브로커/세션 직접 호출 안 함.

### LC2. CommandBus (CommandQueue + CommandWorker)
- **책임**: **브로커 *변이* + executor 커서를 만지는 유일한 스레드.** **2-레인 큐(emergency / normal)**를 드레인하여 직렬 처리:
  사람 거래(`execute_decision`), `/flatten`·`/flatten all`·`/kill`의 청산/취소, `/stop`, `/cancel`, 승인 실행(`/approve`),
  스케줄러의 executor 단계(`execute_pending`/`run_risk_exits`), 읽기 조회(positions/orders/status 스냅샷).
- **우선순위(검토 #1)**: 응급 명령(`/kill`·`/flatten all`·`/flatten`·`/pause`·`/halt-entries`)은 **emergency 레인**으로
  대기 중 normal 작업보다 앞서 처리. 다심볼 executor 단계는 **심볼 사이마다 emergency 레인을 점검하고 양보**.
  worst-case 응급 지연 = 진행 중인 **단일 심볼** 사이클(~11s: cancel_and_wait 6s + submit fill-poll ~5s, 검토 #3).
- **스레드**: 단일 워커 스레드. 사이클마다 보유/주문 **캐시 스냅샷** 갱신(툴바/`is_market_open` 캐시 공급).
- **상호작용**: `DecisionExecutor`/`RiskManager`/`Broker`(기존), `SteeringState`(state_lock), `Notifier`(승인 알림 push).
- **불변식(정밀, 검토 #1/#7/#8)**: **데몬 내부 브로커 변이 + 커서**는 여기서만 → 그 레이스는 0(NFR-1). **읽기 전용**
  `is_market_open`/시세는 캐시 스냅샷 우선. **단, 에이전트 `claude` 서브프로세스는 별도 프로세스에서 자체 `AlpacaBroker`로
  `tools account`를 호출(라이브 읽기, tools/__main__.py:21-30)** — 데몬 캐시와 무관·불일치 가능(읽기뿐이라 안전).
  전역 "단일 브로커 스레드" 표현 금지; `src/agent/tools`는 read-only 유지가 계약. `decisions.jsonl`은 cross-axis → torn-line 방어(LC7).

### LC3. TurnCoordinator (turn_lock)
- **책임**: `AgentSession` 호출 직렬화(동시 `claude --resume` 금지).
- **보유자**: 예약 LLM 턴(research/intraday/eod), ReconcileWorker.
- **상호작용**: `AgentTradingLoop`/`AgentSession`(기존). 브로커 비점유 → 긴 턴이 CommandBus를 막지 않음.

### LC4. ReconcileWorker
- **책임**: 사람 거래/`/directive`/승인 해소 후 **디바운스된 async reconcile 턴** 실행.
- **스레드**: 백그라운드(트리거 시). `turn_lock`을 **bounded blocking + 다음 예약 턴보다 우선권**(CQ-R1=A)으로 획득 →
  `orchestrator.run_reconcile(context)` → 해제. max-staleness = 진행 중 턴 잔여시간(기아 없음, FR-6 "즉시" 근접).
- **회복성**: best-effort(try/except, 데몬 비중단), coalesce.
- **컨텍스트 입력**: 직전 reconcile 이후 사람 개입, 라이브 보유, 락/denied/pending 상태.

### LC5. SteeringState (+ 영속 스토어, state_lock)
- **구성**:
  - `RunState`(paused/entries_halted) — 인메모리 + **ET-date 영속**(`run_state.json`, CQ-D1=A): 같은 거래일 재시작 복원, 다음 거래일 running.
  - `HumanLockStore` → `human_locks.json`(ET-date).
  - `PendingApprovalStore` → `pending_approvals.jsonl`(ET-date).
  - `DirectiveStore` → `directives.jsonl`.
  - `InterventionLog` → `human_directives.jsonl`(append-only, 영구).
  - `snapshot`(보유/주문 캐시) — 인메모리, CommandBus가 갱신.
- **책임**: 상태 보관·영속·ET-date 만료. pydantic 직렬화(SECURITY-13).
- **ET-date 만료(검토 #2)**: **접근마다 lazy 만료**(읽을 때 `entry.date != today_ET`면 제외) **+** 스케줄러의 **ET 자정
  sweep 잡**(만료분 정리·재기록). "로드 시 1회"만으로는 24/7 데몬이 자정을 넘기면 어제 상태가 잔존하므로 불충분.
- **id 재수화(검토 #3)**: PendingApproval/Directive의 "당일 단조 증가" id는 **로드 시 카운터 = 기존 최대 id + 1**로 시드
  (같은 날 재시작 시 #1,#2 충돌 방지).
- **락 해제 시 outstanding PendingApproval 해소(검토 #6)**: `/unlock <SYM>`·자정 sweep으로 락이 풀리면, 해당 종목의
  `status="pending"` 승인건을 그대로 두지 않고 **`rejected`/`expired`로 해소**(콘솔/`/pending`에 유령 항목 방지, 에이전트 피드백).
  sweep은 `state_lock` 하에 수행; parking은 멱등이라 sweep↔parking 경합 시 swept-then-reparked는 허용.
- **동시성**: `state_lock`로 보호(O(1) 연산). 읽기: ConsoleThread(툴바/status), Executor(게이팅). 쓰기: CommandWorker.

### LC6. CommandParser
- **책임**: 슬래시 문법 파싱→구조화 `Command`(verb+args), 크기 단위 검증(`$`/`sh`/`%`), 거부+사유.
- **순수성**: 부수효과 없는 순수 함수(테스트·PBT 대상). **속성(PBT-03)**: 유효 크기 없는 거래 명령 미산출; `%`→(0,1]; trade→source=human.

### LC7. Executor 확장 (기존 `DecisionExecutor`)
- **변경**: 에이전트 결정 처리 시 `HumanLockStore` 조회 →
  `locked`&BUY/SELL → `PendingApproval` 생성(보류)+Notifier; `denied`&BUY/SELL → 자동 거부+에이전트 피드백;
  보호주문(ADJUST_STOP/HOLD+stop/OCO수정) → 즉시 실행(예외); 그 외 → 기존대로.
- **신규 메서드(논리)**: `execute_decision(decision)`(사람 거래 직접 실행, 커서 무관), 게이팅 훅.
- **멱등 parking + 점진 커서(검토 #4)**: PendingApproval 생성은 decision 지문 키로 멱등(중간 실패 재실행 시 중복 방지);
  커서는 결정 단위로 점진 저장(배치 끝 1회 → 처리마다). 게이팅은 **주문 제출 *이전*** 분기라, 게이트된 결정은 재실행돼도 재제출 안 됨.
- **torn-line 방어(검토 #8, 현재 미구현→코드젠 추가)**: `read_decisions`(현 splitlines, journal.py:110)는 개행 미종료
  마지막 청크를 **파싱 전 제거**; 커서는 **완전한 물리적 줄 수** 기준(parsed-and-filtered 길이 아님 → 기존 skip 커서 드리프트 제거).
- **스레드**: 항상 CommandBus(LC2) 위에서 실행.

### LC8. Notifier
- **책임**: CommandWorker/ReconcileWorker → ConsoleThread로 async 메시지(승인 대기/완료/실패) 전달, `patch_stdout`로 렌더.
- **구현(논리)**: 스레드 안전 콜백/큐 + prompt_toolkit `run_in_terminal`/`patch_stdout`.

### LC9. main.py / modes/agent 통합
- **변경**: `AgentTradingMode`가 CommandBus·TurnCoordinator·ReconcileWorker·SteeringState·SteeringConsole를 조립.
  스케줄러 잡들이 LLM 단계는 turn_lock으로, executor 단계는 CommandBus로 enqueue하도록 재배선.
  메인 스레드는 TTY면 콘솔 루프, 아니면 기존 sleep-wait.
- **스케줄러 스레드의 브로커 터치 재배선(검토 #7)**: `agent.py:63 _intraday`의 `broker.is_market_open()` 등 스케줄러
  스레드에서의 직접 브로커 호출은 **CommandWorker가 갱신하는 캐시 스냅샷**(market-open/clock)을 읽도록 변경.
  부득이한 직접 읽기만 허용(부수효과 없음). 재배선 체크리스트: market-open 가드, `_update_market_halt`, 게이팅 조회.
- **신규 잡 등록(검토 #2)**: ET 자정 sweep 잡(락/pending/directive 만료 정리) 추가.
- **monitor.sh**: 데몬+콘솔을 한 패널에서 실행(CQ5=A).

---

## 스레드 × 컴포넌트 × 락 매트릭스
```
스레드            관여 컴포넌트                        보유 락
ConsoleThread     LC1 SteeringConsole, LC6 Parser       (state_lock 읽기)
CommandWorker     LC2 CommandBus, LC7 Executor, LC5     state_lock(쓰기 시)
Turn/scheduler    LC3 TurnCoordinator, AgentSession     turn_lock
ReconcileWorker   LC4 ReconcileWorker, orchestrator     turn_lock
```
- 브로커 **변이+커서**: **CommandWorker 전용**(읽기 전용 market-open/시세는 캐시 스냅샷 우선). LLM 세션: **turn_lock 보유
  스레드 전용**. 두 축 독립 → 긴 턴이 거래 명령을 막지 않음(단 응급 명령은 emergency 레인으로 선점, worst-case ~6s).

## 데이터 저장 위치 (workspace/)
| 파일 | 내용 | 스코프 |
|---|---|---|
| `human_directives.jsonl` | InterventionRecord(감사) | append-only 영구 |
| `human_locks.json` | HumanLock 상태 | ET-date |
| `pending_approvals.jsonl` | PendingApproval | ET-date |
| `directives.jsonl` | 상시 지시 | 활성/해제 |
| `run_state.json` | RunState(pause/halt) | ET-date (CQ-D1=A) |
| `pending_human_trades.jsonl` | 폐장 중 사람 거래 보류 | ET-date (CQ-R2=A; open 잡이 드레인) |
| (기존) `decisions.jsonl` | 에이전트 결정 | 사람 거래 미포함(멱등성 보존) |

## 회복/장애 시나리오
- 콘솔 예외 → 로그+격리, 데몬 거래 지속. 비-TTY → 콘솔 off.
- reconcile 실패 → 로그, 다음 트리거/예약 턴에서 재정렬.
- 같은 날 데몬 재시작(크래시/수동) → locks/pending/directives **및 RunState(pause/halt) 영속 복원**(CQ-D1=A); 다음 거래일엔 running.
- 긴 research 턴 중 `/kill` → turn_lock 무관하게 CommandBus emergency 레인에서 우선 처리(worst-case ~11s 진행 중 단일 심볼 사이클 대기, 검토 #3)+pause.
- ET 자정을 데몬이 재시작 없이 넘김 → lazy 만료 + sweep 잡으로 어제 락/pending 자동 해제(검토 #2).
- 크래시 자동 재시작(같은 거래일) → RunState(pause/halt)도 영속 복원되어 보호적 정지 유지(검토 #9 해결, CQ-D1=A).
