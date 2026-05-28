# 도메인 엔티티 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · Functional Design · 2026-05-29._
_기술 비종속 설계. 코드 식별자/경로는 영문 유지, 설명은 한국어._

본 유닛이 도입/확장하는 도메인 개념과 그 관계를 정의한다. 인프라 관심사는 NFR Design에서 다룬다.

---

## E1. `Decision.source` (기존 `Decision` 확장)
기존 `src/agent/journal.py::Decision`에 출처 태그를 추가한다.

| 필드 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `source` | `Literal["agent","human"]` | `"agent"` | 결정의 출처. 기존(에이전트) 결정은 모두 `"agent"`로 호환. 콘솔에서 사람이 강제한 거래는 `"human"`. |

- 하위호환: 기존 `decisions.jsonl` 라인에 `source`가 없으면 `"agent"`로 파싱(기본값).
- 용도: 저널/로그/EOD에서 사람 거래와 에이전트 거래 구분, 그리고 사람-락 트리거 판정.

## E2. `InterventionRecord` (사람 개입 영구 로그)
모든 콘솔 개입을 구조적으로 남기는 append-only 레코드. 저장: `workspace/human_directives.jsonl`.
(요구사항 Q7=A — 구조적 로깅, 학습은 추후.)

| 필드 | 타입 | 설명 |
|---|---|---|
| `ts` | `datetime` | 발생 시각 |
| `kind` | `Literal["trade","lifecycle","note","directive","approval","lock"]` | 개입 분류 |
| `raw` | `str` | 사용자가 친 원문 (예: `/sell AAPL 50%`) |
| `command` | `str` | 파싱된 동사 (예: `sell`, `pause`, `approve`) |
| `args` | `dict` | 파싱된 인자 (symbol, size, unit, price, id 등) |
| `outcome` | `str` | `executed`/`no_order`/`rejected`/`skipped`/`error`/`applied`/`cancelled` |
| `detail` | `str` | 사람이 읽을 결과 요약 (체결 수량/가격/주문ID 또는 사유) |
| `rationale` | `str = ""` | 예약 필드. v1에선 거부 사유(`/reject <id> <사유>`)에만 채워짐 |

- pydantic 모델로 직렬화/파싱 (안전 역직렬화, SECURITY-13). 비밀정보 미포함(SECURITY-03).
- **속성(PBT-02):** `InterventionRecord` serialize→deserialize == 원본 (라운드트립).

## E3. `RunState` (lifecycle 실행 상태)
데몬 전역 실행 상태. 인메모리 객체(명령 락으로 보호). **디스크 미영속** — 재시작 시 항상 `running`,
진입 허용으로 시작(Q9=A).

| 필드 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `paused` | `bool` | `False` | `True`면 예약 리서치/진입/intraday 턴이 no-op. 보호·리스크 청산·사람 명령은 계속 동작. |
| `entries_halted` | `bool` | `False` | `True`면 신규 **에이전트 BUY 진입** 차단(기존 포지션 관리/청산/보호 유지). |

- `/status`가 읽어 표시. 스케줄러 사이클이 시작 시 이 상태를 확인해 게이팅.

## E4. `HumanLock` (사람-락 상태머신) — 핵심
사람이 손댄 종목에 대한 에이전트 재량 결정을 승인 게이트에 거는 상태. 종목별·당일 스코프.
저장: `workspace/human_locks.json`, **ET 날짜로 스코프**(로드 시 날짜≠오늘이면 무시 → 다음 거래일 자동 해제,
같은 날 재시작은 유지). 명령 락으로 보호.

```
LockState(per symbol):
  status: Literal["locked", "denied"]
  reject_count: int  # 0,1,2
```

상태 전이 (CQ1=B, CQ3=A + 노트):
```
(없음) --사람 /buy|/sell|/flatten SYM--> locked(reject_count=0)
locked --에이전트 BUY/SELL 결정--> [PendingApproval 생성, 실행 보류]
  └ 사람 /approve --> (락 해제: 종목 제거)  # "한번 허용하면 락 풀림"
  └ 사람 /reject  --> reject_count += 1
        ├ reject_count == 1 --> locked 유지 (에이전트 재요청 가능)
        └ reject_count == 2 --> denied (당일 영구 거부)
denied --에이전트 BUY/SELL 결정--> [자동 거부 + 에이전트에 피드백, PendingApproval 미생성]
locked|denied --사람 /unlock SYM--> (제거)
(임의) --다음 거래일--> (전부 자동 해제)
```

- **예외(락 무관, 항상 자율):** 에이전트의 **보호주문** — 미보호 포지션에 OCO/스탑 등록, 기존 OCO 수정,
  `ADJUST_STOP`, `HOLD`+stop. 불변식 "모든 포지션은 보호되어야 함"을 막지 않기 위함.
- **예외(락 무관, 항상 동작):** resting 보호주문 체결과 폴드 리스크 청산(`run_risk_exits`)은 에이전트 "결정"이
  아니라 안전 장치이므로 게이트와 무관하게 항상 발동.
- **속성(PBT-03):** `reject_count` 단조 증가; `reject_count==2 ⇔ status=="denied"`; `/approve`는 락 제거.

## E5. `PendingApproval` (승인 대기 큐 항목)
에이전트가 사람-락 종목에 대해 낸 재량 결정 중 승인 대기 중인 건. 저장:
`workspace/pending_approvals.jsonl`(ET 날짜 스코프, 재시작 안전). 인메모리 큐 + 영속.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `int` | 당일 단조 증가 ID (`/approve <id>`로 지목) |
| `decision` | `Decision` | 에이전트 제안 결정(`source="agent"`) |
| `created_ts` | `datetime` | 대기 시작 시각 |
| `status` | `Literal["pending","approved","rejected"]` | 처리 상태 |
| `reason` | `str = ""` | 거부 사유(있으면) |

- `/approve <id>` → `decision`을 RiskManager→Broker로 실행, 해당 종목 락 해제, 에이전트 피드백 기록.
- `/reject <id> [사유]` → 실행 안 함, 락 유지+카운트, 에이전트 피드백 기록.

## E6. `Directive` (상시 지시) / Note (일회성 맥락)
- **Note**: `/note <text>` → `InterventionRecord(kind="note")`로 로그. 다음 **예약 턴**에 맥락으로 노출
  (즉시 reconcile 안 함, Q7=A). 별도 저장 구조 없음(로그가 출처).
- **Directive**: `/directive <text>` → 상시 지시. 저장: `workspace/directives.jsonl`(active 목록).
  매 에이전트 턴 프롬프트에 노출 + 등록 시 reconcile 트리거. `/directives` 목록, `/directive clear [id|all]` 해제.

| Directive 필드 | 타입 | 설명 |
|---|---|---|
| `id` | `int` | 지시 ID |
| `ts` | `datetime` | 등록 시각 |
| `text` | `str` | 지시 본문 |
| `active` | `bool` | 활성 여부(clear 시 false) |

---

## 엔티티 관계 요약 (텍스트)
```
콘솔 명령 ── 파싱 ──> InterventionRecord(로그) ──+
                                                  │ (trade)        ┌─ HumanLock(SYM) 생성
                                                  ├──> Decision(source=human) ─> Executor ─> RiskManager ─> Broker
                                                  │ (lifecycle) ──> RunState 갱신
                                                  │ (directive) ──> Directive 저장 + reconcile
                                                  └ (approval) ──> PendingApproval 해소 ─> (approve 시) Executor 실행 / 락 해제

에이전트 결정(Decision source=agent) ─> Executor
   ├ 종목이 HumanLock=locked & 재량(BUY/SELL) ─> PendingApproval 생성(실행 보류) ─> 콘솔 알림
   ├ 종목이 HumanLock=denied  & 재량         ─> 자동 거부 + 에이전트 피드백
   ├ 보호주문(ADJUST_STOP/HOLD+stop/OCO수정)  ─> 즉시 실행(락 예외)
   └ 그 외(락 없음)                           ─> 기존대로 즉시 실행
```
