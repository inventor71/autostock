# NFR 설계 패턴 — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · NFR Design · 2026-05-29._
_입력: `../nfr-requirements/` + `../functional-design/`(BR/E) + /critic 반영 + opencode 조사. 내부 엔지니어링 결정._

핵심 위험은 F2와 동일 — **돌아가는 데몬에 동시성을 더하는 것** + **권한 분리**. F2 패턴(P1~P6)을 detached+file-drop로
적응하고, critic 발견을 반영한다. (prompt_toolkit P5는 폐기 — UI는 Unit B.)

---

## P1. 동시성/직렬화 — 단일 CommandWorker(큐) + turn_lock 분리

### P1.1 직렬화 primitive 결정 (이월 항목 해소)
- **EngineSerialization = 단일 워커 + 큐**(bare Lock 아님). 명령이 **세 소스**(file-drop 폴링 / 스케줄러 executor funnel /
  reconcile·승인)에서 오므로 **`queue` 기반 단일 CommandWorker**가 적합. 이 워커만 **broker *변이* + executor 커서 + 락스토어**를 만진다.
- **funnel(BR-7.1'):** 스케줄러의 `_open_execute/_intraday/_eod`가 `execute_pending`을 *직접* 호출하던 것을(현 `modes/agent.py`)
  **큐 enqueue로 전환**. 직접 호출 금지 → 단일-워커 불변식 성립.
- **응급 레인(BR-13):** 2-레인(emergency/normal) 또는 PriorityQueue. 응급 verb(`kill`/`flatten_all`/`flatten`/`pause`/`halt_entries`)는
  *대기 중* normal보다 앞섬. 다심볼 executor 단계는 **심볼 사이마다 emergency 레인 점검 후 양보**. *진행 중* 단일 broker
  호출은 선점 불가(worst-case ~11s — `_cancel_and_wait`6s+`_poll_for_fill`5s, 명시 수용).
- **TurnLock = LLM 세션 직렬화**: `AgentSession` 호출은 `turn_lock` 경유(예약 턴 + reconcile). LLM 턴은 저널만 쓰고
  broker 미접촉 → turn_lock만 보유, Engine 비점유(긴 research가 응급을 안 막음).

### P1.2 TurnCoordinator (신규 — C-1 선반영)
- `turn_lock`(threading.Lock) + **"turn in-flight" 플래그를 waiter 카운트와 분리**.
- `reconcile_turn()`: bounded-blocking acquire + **다음 예약 턴보다 우선권**(CQ-R1=A; 무한 양보 기아 방지).
- `try_scheduled_turn()`: **non-blocking acquire — 점유 중이면 스킵**(F3 skip-if-busy가 그냥 호출이 되도록; reconcile-yield와
  구분). 스케줄러 `add_job`에 **`max_instances=1, coalesce=True` 명시**(현 기본값 암묵 의존 제거). 동일 `session_id`에
  `claude --resume` 2개 동시 불가를 테스트로 고정.

### P1.3 불변식 정밀화 (BR-7.2', /critic #2)
- "broker 변이+커서 단일 스레드"는 **데몬 내부**에 한정. 에이전트 서브프로세스는 자체 `AlpacaBroker`로 **read-only** account/
  orders를 봄(`tools/__main__.py`) — 별도 라이브 *읽기* 클라이언트(커서·주문 무해). `src/agent/tools`는 read-only 유지.
- 읽기 전용(`is_market_open`/시세)은 다른 스레드 호출 가능하나, 네트워크 절감 위해 **snapshot 캐시**(publisher 갱신) 사용.

### P1.4 SteeringState 동시 접근
- 인메모리(RunState/HumanLock/PendingApproval/Directive)는 다수 스레드 읽기(게이팅·snapshot) + CommandWorker 쓰기 →
  빠른 `state_lock`(threading.Lock)으로 O(1) dict 보호. 영속 파일 쓰기도 이 락 안 + 원자적(temp+`os.replace`).

### P1.5 ET-date lazy 만료 + 자정 sweep (F2 계승)
- 데몬은 재시작 없이 며칠 돈다 → ET-date 스코프 상태(lock/denied/pending/run_state)는 **(a) 접근마다 lazy 만료** +
  **(b) ET 자정 sweep 잡**(만료분 정리 + 영속 재기록). 같은 날 재시작은 영속 파일로 복원(BR-3.3/4.8).

## P2. 회복성(Resilience)
- **스레드 격리**: file-drop 리더(폴 잡)·CommandWorker·ReconcileWorker·스케줄러·snapshot publisher 각각 최상위 try/except —
  예외는 로그만, **데몬 비중단**(BR-8.2, SECURITY-15).
- **Fail-closed**: 미확인/스키마위반/토큰실패 → no-op + error 이벤트. 워커 명령 에러 → `outcome=error` 이벤트, 큐 계속.
- **Best-effort reconcile (C-4)**: ReconcileWorker는 **트리거 유형별 run_fn/프롬프트**(단일 고정 금지), 단일 turn_lock,
  유형별 디바운스. 모든 발화는 단일 `reconcile_turn()` 봉투. 경합 스킵은 **명시 경고 로그**(조용한 유실 금지).
- **멱등성**: 사람 거래는 공개 `execute_decision(Decision)`(커서 무접촉, `_execute_one` 승격) — `decisions.jsonl`/커서 미접촉.
  PendingApproval parking은 decision 지문 키로 멱등. file-drop는 바이트오프셋 커서 + **`id` dedup 권위**(BR-11).
- **torn-safe 리더(BR-11.1, C-5)**: 마지막 `\n`까지만 소비, 바이트오프셋 커서, 공유 헬퍼(commands/decisions/agent_questions).
  Unit B는 commands.jsonl 원자적 append.

## P3. 성능
- 단일 워커, 저빈도. **file-drop 폴 1–2s**, **snapshot publisher 2–5s**(별도 주기 — 이월 항목 해소; broker 호출
  예산 계상, staleness 상한 = publisher 주기). snapshot/cursor/state 쓰기는 원자적(temp+`os.replace`).
- 읽기(status/positions/orders)는 운영자가 `snapshot.json` 직접 읽음 → 데몬 라운드트립·블로킹 0.

## P4. 보안 (강제) — 권한 분리가 이번 유닛 핵심
- **SECURITY-11:** **BR-10 권한 분리.**
  - *주축:* `AgentSession` **PreToolUse 훅(필수)** — `Read/Write/Edit/Glob/Grep`의 `workspace/` 밖 경로 deny(P5' 상세).
  - *토큰:* 데몬 생성, 파일/데몬env 비저장, 운영자 프로세스에만 out-of-band, **에이전트 spawn env에서 scrub**(P5').
  - *위치:* commands 채널은 workspace 밖. *잔존:* advisor-only(주문 직접 불가) + executor 승인 게이트.
  - 스티어링/주문배치 분리(executor/RiskManager 재사용, 신규 주문 경로 0). 오남용: `flatten_all`/`kill` 강확인(Unit B).
- **SECURITY-03:** 토큰/비밀 비기록(이벤트·로그). **SECURITY-13:** pydantic 안전 역직렬화 + append-only 감사.
  **SECURITY-15:** P2 fail-closed/격리/finally. **SECURITY-10:** Unit A 신규 런타임 deps 0(핀 불요; opencode는 Unit B).

## P5'. file-drop I/O + 훅 패턴 (F2 prompt_toolkit P5 대체)
- **file-drop in:** APScheduler 폴 잡(1–2s) → 공유 torn-safe 리더로 신규 완전 라인 → 검증(`confirmed`+토큰+스키마) → dedup(id) →
  CommandQueue enqueue(응급 레인 분기). 커서 영속 원자적.
- **file-drop out:** CommandWorker가 outcome(`corr_id`) / fill / pending / agent_question / reconcile 이벤트를 events.jsonl append.
  snapshot publisher가 snapshot.json 원자 게시.
- **PreToolUse 훅(에이전트=claude):**
  - settings.json에 PreToolUse 매처 → **결정적 Python 거부 스크립트**가 tool input의 경로를 `realpath`로 정규화,
    **workspace 루트 하위가 아니면 deny**(절대경로/`..` 탈출 차단). `Read/Write/Edit/Glob/Grep`에 적용.
  - **Bash 주의:** 임의 bash 경로 파싱은 취약 → Bash는 기존 **`Bash(python -m src.agent.tools:*)` 화이트리스트 + exec-form/
    인자검증**으로 2차 명령 차단(훅으로 bash 경로검사에 의존하지 않음). 즉 Bash는 allowlist가, 파일도구는 훅이 경계.
  - 로드 위치: `workspace/.claude/settings.json`(에이전트 cwd) 우선, 대안 `--settings`/프로젝트 settings — **코드젠 실측**.
    `--permission-mode dontAsk`여도 훅 hard-deny 유효.
  - **토큰 scrub:** `session._invoke`의 `env = dict(os.environ)`에서 운영자 토큰 키를 **pop**(에이전트에 누수 차단).
- **confirm 무결성(P6 — Unit B 책임, 여기 계약만):** `confirmed=True`는 opencode **커스텀 툴 execute 함수**(결정적)가 사람
  확인 후 설정(LLM 위조 불가) + `task` deny. 데몬측 토큰+RiskManager가 최종 경계. (상세 `operator-tool/.../opencode-feasibility.md`.)

## 패턴 ↔ NFR/규칙 추적
| 패턴 | 충족 |
|---|---|
| P1 단일 워커+큐+funnel+응급레인 / TurnCoordinator(in-flight, try_scheduled) | NFR-1, BR-7, BR-13, C-1/#2/#3 |
| P1.5 lazy 만료+자정 sweep | BR-3.3/4.8 |
| P2 격리·fail-closed·per-trigger reconcile·멱등·torn-safe | BR-6/8/11, SECURITY-15, C-4/C-5/#4/#5 |
| P3 비블로킹 읽기·publisher 주기 | 성능, C-3/#6 |
| P4+P5' 권한 분리(훅+토큰+위치)·file-drop I/O | BR-10/12, SECURITY-03/10/11/13/15, #1 |
| P6(계약) confirm 무결성 | Q4=B, opencode 조사 |
