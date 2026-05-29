# 비즈니스 로직 모델 — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · Functional Design · 2026-05-29._

명령 **계약(스키마)**, 검증 규칙, file-drop을 통과하는 데이터 흐름을 정의한다.
(슬래시 문법·자연어 해석·`y/N` 확인은 **Unit B**의 책임 — 여기서는 데몬이 받는 *확정 구조화 명령*만 다룬다.)

---

## 1. 명령 계약 (file-drop `SteeringCommand`)
운영자 도구가 자연어/슬래시를 **결정적 `verb`+`args`** 로 환원해 보낸다. 데몬은 verb별로 검증·실행.

### 1.1 거래 (executor 게이트 통과)
| verb | args | 의미 | 락 |
|---|---|---|---|
| `buy` | `symbol`, `size`, `unit∈{$,sh}` | 강제 매수 | HumanLock 생성 |
| `sell` | `symbol`, `size`, `unit∈{%,sh,$}` | 강제 매도 | HumanLock 생성 |
| `flatten` | `symbol` | 종목 100% 청산 + resting 취소 | HumanLock 생성 |
| `flatten_all` | — | 전 종목 청산 + 전체 resting 취소 | 각 종목 락 |
| `stop` | `symbol`, `price` | 보호 스탑 설정/조정 | **락 없음**(보호 관리) |

### 1.2 lifecycle
| verb | 의미 |
|---|---|
| `pause`/`resume` | 예약 리서치/진입/intraday 턴 정지/재개(보호·청산·사람명령 유지) |
| `halt_entries`/`allow_entries` | 신규 에이전트 BUY 진입 차단/허용 |
| `kill` | `flatten_all` + `pause` |

### 1.3 승인 / 락
| verb | 의미 |
|---|---|
| `approve` (`id`) | 승인 → 게이트 실행, 종목 락 해제, 에이전트 피드백 |
| `reject` (`id`,`reason?`) | 거부 → 미실행, 락 카운트++ (2회→denied), 피드백 |
| `unlock` (`symbol`) | 락/denied 수동 해제 + outstanding pending 해소(BR-4.10) |

### 1.4 맥락 / 양방향
| verb | 의미 | reconcile |
|---|---|---|
| `note` (`text`) | 일회성 맥락 로그 | 안 함 |
| `directive` (`text`) | 상시 지시 등록 | 함 |
| `directive_clear` (`id\|all`) | 지시 해제 | — |
| `answer` (`id`,`text`) | `AgentQuestion`에 답(FR-7) | 함 |

### 1.5 읽기 (file-drop 불필요 — 운영자 도구가 `snapshot.json`/journal 직접 읽음)
`status`·`positions`·`orders`·`agent-trace`·`log` 등은 **명령 채널을 타지 않는다**. 운영자 도구는
`steering/snapshot.json`(라이브 뷰, C-3 보강)과 `workspace/`의 journal/trace를 read-only로 읽어 표시.
→ 읽기는 직렬화 경로·토큰과 무관(부수효과 0).

---

## 2. 검증 규칙 (데몬측, 결정적)
1. `SteeringCommand`는 pydantic로 파싱 — 스키마 위반 → 거부 + `SteeringEvent(outcome=error, detail=사유)`.
2. **`confirmed != True` → 거부**(Q2=A, fail-closed). 데몬은 확인을 대행하지 않는다.
3. **`token` 검증 실패/누락 → 거부 + 로그**(BR-10; 토큰 값은 로그에 남기지 않음).
4. 심볼 대문자 정규화. size 단위 검증: `$`>0 / `sh`>0(분수 허용) / `%`→(0,1] frac(`sell`만).
5. 단위 누락/미허용 → 거부 + 사유. **부분 실행 금지**(fail-closed).
6. **(PBT-03):** 검증기는 유효 size 없는 거래 verb를 실행 형태로 통과시키지 않는다; 거래 결과 `source`는 항상 `"human"`.

---

## 3. 데이터 흐름

### 3.1 운영자 → 데몬 (file-drop in)
```
[Unit B 운영자 도구]  자연어/슬래시 → 환원(verb,args) → echo → 사람 y/CONFIRM 확인
        └─ 확정 시 → steering/commands.jsonl 에 SteeringCommand(confirmed=True, token, id) append
                                  │
[데몬] file-drop 리더(스케줄러 폴링 잡, 1–2s; Q3=A)
        └─ 신규 *완전* 라인만 읽기(공유 JSONL 리더 + torn-line 가드; C-5) → 커서 영속(BR-11)
        └─ 각 레코드 검증(§2) → CommandQueue enqueue (응급 verb는 emergency 레인; P1)
                                  │
        CommandWorker(단일 스레드) ── 직렬 ── 브로커/executor/커서/락스토어 변이
        (스케줄러측 executor 호출도 이 큐로 funnel — BR-7.1'; 응급은 *대기* 작업보다 우선하나
         *진행 중* broker HTTP는 선점 불가 → worst-case ~11s, "즉시" 아님, BR-13)
        └─ 처리 후 SteeringEvent(kind=outcome, corr_id=cmd.id, payload) → steering/events.jsonl
```

### 3.2 CommandWorker 처리 (verb별)
- **거래**: `Decision(source="human")` 구성 → **단일-결정 실행 경로**로 RiskManager→Broker 통과 → HumanLock 생성 →
  `InterventionRecord` → async reconcile 트리거. (장 마감 시 BR-2.7: `pending_human_trades` 큐 적재, 개장 잡이 드레인. 락 즉시 생성.)
  - **⚠ /critic #4 정정:** `main`에 `execute_decision`는 **없다** — `DecisionExecutor`엔 `execute_pending()`(커서 결합,
    *모든* 에이전트 pending을 드레인 + 커서 전진, `executor.py:89-120`)와 private `_execute_one(d)`(커서 미접촉,
    `:123-160`)만 존재. → **`_execute_one`을 공개 `execute_decision(Decision)`로 승격**해 사용: `decisions.jsonl`/커서를
    읽지도 쓰지도 않고, **market-open/off-hours 큐 판정을 스스로** 수행(`execute_pending`의 장중 게이트 `:92`가 안 도므로).
    사람 거래에 `execute_pending()`을 쓰면 에이전트 pending까지 동반 실행 + 커서 전진(멱등성 위반) — 금지.
- **lifecycle**: `RunState` 갱신(ET-date 영속) → 로그 → (kill/flatten_all은 거래+상태 변경).
- **approval**: `approve`→PendingApproval.decision 실행+락 해제+피드백+reconcile / `reject`→카운트++/denied+피드백.
- **unlock/cancel/stop**: 브로커·락 연산 → 로그. `cancel`이 보호 제거 시 경고(폴드 청산 백업은 유지, BR-8.4).
- **note/directive/answer**: 로그/저장 + (directive·answer는 reconcile 트리거).
- 모든 결과는 `corr_id=cmd.id` outcome 이벤트로 게시(Q4=A).

### 3.3 에이전트 결정 경로 (executor 게이트 — F2 그대로 계승)
에이전트가 쓴 `Decision(source="agent")`을 executor가 처리할 때:
```
종목 락 상태?
 ├ locked  & 동작∈{BUY,SELL}        → PendingApproval 생성(멱등: decision 지문 키; P2), 보류, 이벤트 push
 ├ denied  & 동작∈{BUY,SELL}        → 자동 거부 + 에이전트 피드백, 미실행
 ├ 보호주문(ADJUST_STOP/HOLD+stop/OCO) → 즉시 실행(락 예외, BR-4.6)
 └ 락 없음                           → 기존대로 즉시 실행
```
- resting 보호 체결 / `run_risk_exits()`(폴드 청산)는 **항상** 동작(안전, 게이트 무관).
- PendingApproval 생성 시 `SteeringEvent(kind=pending)` push(운영자 알림); 신규 fill은 `kind=fill` push.

### 3.4 reconcile (async, turn_lock 공유) — C-4 반영
- 트리거: 사람 거래 / directive / answer / approve·reject로 장부 변경 직후.
- 실행: ReconcileWorker가 **트리거 유형별 run_fn/프롬프트**(C-4 — 단일 run_fn 고정 금지)를, 예약 턴과 **turn_lock 공유**.
  bounded blocking + 다음 예약 턴보다 우선(CQ-R1=A). 다수 개입은 디바운스 1회 합침.
- best-effort: 실패는 로그만, 데몬 비중단(BR-6.3).

### 3.5 양방향 질의 (FR-7)
```
에이전트 → workspace/agent_questions.jsonl (status=open) append
데몬(폴링) → 신규 open 질문 → SteeringEvent(kind=agent_question) push
운영자 → verb=answer(id,text) → 데몬: 질문 answered 갱신 + reconcile (에이전트가 다음 턴에 답 반영)
```

---

## 4. 에이전트 피드백 ("무한 재시도 방지") — F2 §4 계승
승인/거부/denied 결과는 `InterventionRecord(kind=approval)` + 에이전트 저널/프롬프트 맥락으로 기록 →
에이전트가 "왜 안 됐는지" 이해하고 같은 시도를 반복하지 않게.

---

## 5. F3 critic 발견의 선반영 (재구현 이점)
Unit A는 엔진을 새로 짜므로 F3가 지적할 사항을 **처음부터** 설계에 넣는다:
- **C-1**: TurnCoordinator는 "turn in-flight" 플래그를 waiter 카운트와 분리하고 `try_scheduled_turn()`(점유 시 스킵)을 제공 →
  F3의 skip-if-busy가 "기존 primitive 수정"이 아니라 그냥 호출이 되도록.
- **C-3**: `snapshot.json` 페이로드를 positions/open_orders/fills 커서까지 확장(§E Snapshot) + 짧은 주기 갱신.
- **C-4**: ReconcileWorker는 트리거 유형별 run_fn/프롬프트(단일 고정 금지), 단일 turn_lock, 유형별 디바운스.
- **C-5**: "완전 JSONL 라인 읽기 + 영속 커서" 헬퍼를 **공유 모듈**로 추출(commands/decisions/agent_questions/watch가 재사용).
- (F3 전용 watch.jsonl/news는 F3에서 추가하되 위 헬퍼·snapshot·coordinator 위에 얹음.)

## 6. Unit B(운영자 도구)와의 계약 표면 (seam)
Unit A가 **소유·정의**하고 Unit B가 **준수**하는 것:
- `SteeringCommand` 스키마(E7) + 허용 verb/args + `confirmed`/`token` 규칙.
- `SteeringEvent` 스키마(E8) + `corr_id` 상관.
- `snapshot.json` 스키마(읽기 뷰).
- 토큰 발급/전달 메커니즘(BR-10) — Unit B가 토큰을 읽어 명령에 실음(운영자만 접근, 에이전트 비접근).
- (자연어→verb 환원, 확인 UX, tail/렌더는 **Unit B** 책임 — Unit A 범위 밖.)
- **confirm 무결성 계약(opencode 조사 반영):** 운영자측은 LLM이므로, `confirmed=True`는 **LLM이 만질 수 없는
  결정적 레이어**(opencode 커스텀 툴의 execute 함수)가 사람 확인을 받아 설정해야 한다 — LLM이 `confirmed`를 위조
  못 하게. Unit A는 이를 *신뢰*하되, **데몬측 토큰+RiskManager 게이트가 최종 경계**(opencode 잠금은 defense-in-depth).
  상세·알려진 opencode 버그/완화: `../../operator-tool/nfr-requirements/opencode-feasibility.md`.
