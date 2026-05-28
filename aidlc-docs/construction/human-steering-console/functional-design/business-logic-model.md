# 비즈니스 로직 모델 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · Functional Design · 2026-05-29._

명령 문법, 파싱 규칙, 그리고 콘솔 입력이 시스템을 통과하는 데이터 흐름을 정의한다.

---

## 1. 명령 문법 (전부 `/command` 슬래시 접두)
비-슬래시 입력은 거부하고 힌트 표시(fail-closed). `<...>`=필수, `[...]`=선택.

### 1.1 거래 (확인 필요)
| 명령 | 의미 | 크기 단위 | 확인 |
|---|---|---|---|
| `/buy <SYM> <N$\|Nsh>` | 강제 매수 | `$`(노셔널) 또는 `sh`(주식 수)만. 단위 없거나 다른 것 → 거부+사유 | `[y/N]` |
| `/sell <SYM> <N%\|Nsh\|N$>` | 강제 매도 | `%`(보유 비율)·`sh`·`$` 셋만. 항상 명시 | `[y/N]` |
| `/flatten <SYM>` | 해당 종목 100% 청산 + 그 종목 resting 주문 취소 | — | `[y/N]` |
| `/flatten all` | 전 종목 청산 + 전체 resting 주문 취소 | — | **강확인(CONFIRM)** |
| `/stop <SYM> <price>` | 보유 포지션 보호 스탑 설정/조정(사람 설정 보호) | 가격 | `[y/N]` |

- `/buy`,`/sell`,`/flatten`,`/flatten all`은 RiskManager→Broker 동일 게이트 통과(요구사항 Q6=A).
- `/buy`,`/sell`,`/flatten`(및 `/flatten all`의 각 종목)은 해당 종목에 **HumanLock 생성**(E4).
- `/stop`은 **보호 관리** 행위 — 로그+reconcile 대상이나 **락 트리거 아님**(방향성 베팅이 아님).

### 1.2 lifecycle (확인 필요)
| 명령 | 의미 | 확인 |
|---|---|---|
| `/pause` / `/resume` | 신규 리서치/진입/intraday 턴 정지/재개(보호·청산·사람명령은 유지) | `[y/N]` |
| `/halt-entries` / `/allow-entries` | 신규 **에이전트 BUY 진입** 차단/허용 | `[y/N]` |
| `/kill` | `/flatten all` + `/pause` | **강확인(CONFIRM)** |

- `halt-entries` 중에도 사람 `/buy`는 명시적 오버라이드로 실행(단 경고 표시).

### 1.3 승인 (사람-락 종목에 대한 에이전트 결정 처리)
| 명령 | 의미 |
|---|---|
| `/pending` | 승인 대기 중인 에이전트 결정 목록(id/종목/동작/크기/레벨/에이전트 사유) |
| `/approve <id>` | 승인 → 게이트로 실행, 해당 종목 락 해제, 에이전트 피드백 기록 |
| `/reject <id> [사유]` | 거부 → 미실행, 락 유지+카운트++(2회 시 당일 denied), 에이전트 피드백 기록 |
| `/unlock <SYM>` | 사람-락/denied 수동 해제(이후 그 종목 에이전트 거래 다시 자동) |

### 1.4 맥락/스티어링
| 명령 | 의미 | reconcile |
|---|---|---|
| `/note <text>` | 일회성 맥락 로그 | 안 함(다음 예약 턴에 노출) |
| `/directive <text>` | 상시 지시 등록 | **함**(등록 즉시 async) |
| `/directives` | 활성 지시 목록 | — |
| `/directive clear [id\|all]` | 지시 해제 | — |

### 1.5 읽기/보조 (확인 없음, 변이 명령만 확인)
| 명령 | 의미 |
|---|---|
| `/status` | run-state(running/paused/halt) + 승인대기 수 + 락 종목 + 주문 요약 |
| `/positions` (별칭 `/book`) | 현재 보유 포지션 |
| `/orders` | 미체결/resting 주문 목록 |
| `/cancel <SYM>` | 해당 종목 미체결 주문 취소 `[y/N]` — 보호 제거 시 경고(폴드 청산 백업은 유지) |
| `/log [n]` | 최근 로그 n줄(기본 20) — 로그는 파일로만 가므로 콘솔에서 엿보기용 |
| `/help [cmd]` | 명령 도움말(그룹별), `/help <cmd>` 상세 |

## 2. 파싱 규칙
1. 입력 trim 후 `/`로 시작하지 않으면 거부: `알 수 없는 입력 ('/help' 참고)`.
2. 첫 토큰 = 명령. 미등록 명령 → 거부+`/help` 안내.
3. 심볼은 대문자 정규화(기존 `Decision` 규약과 동일).
4. 크기 토큰 파싱 — 접미사로 판정:
   - `…$` → 노셔널(float>0). `…sh` → 주식 수(float>0, 분수 허용 — 기존 분수 매도 정책과 일치).
   - `…%` → 비율(0<p≤100 → 0<frac≤1). `/sell`에서만 허용.
   - 접미사 없음/미허용 단위 → **거부 + 사유**(예: `크기 단위가 필요합니다: $ 또는 sh — 예) /buy AAPL 1000$ | /buy AAPL 5sh`).
5. 파싱 실패/검증 실패는 **부분 실행 금지**(fail-closed): 아무 것도 실행하지 않고 사유만 출력.
6. **속성(PBT-03):** 파서는 유효 크기 스펙 없는 거래 명령을 절대 실행 가능 형태로 산출하지 않는다;
   `%`는 항상 (0,1] frac으로; 거래 파싱 결과의 `source`는 항상 `"human"`.

## 3. 데이터 흐름

### 3.1 콘솔 입력 처리 (요지)
```
입력 ─ parse ─┬ 읽기(/status,/positions,/orders,/log,/help,/pending,/directives)
              │     └─> 브로커/저널/상태 조회 후 즉시 출력 (큐 불필요)
              │
              ├ note ──> InterventionRecord(note) 기록 ; (reconcile 안 함)
              ├ directive ──> Directive 저장 + InterventionRecord ; async reconcile 트리거
              │
              └ 변이(거래/lifecycle/approval/cancel/unlock/stop)
                    └─> 해석 에코 ──> 확인(y/N 또는 CONFIRM)
                          └─ 거부/타임아웃 ─> no-op (fail-closed)
                          └─ 승인 ─> 직렬화 명령 경로(NFR-1)에 enqueue
```

### 3.2 직렬화 경로에서의 처리(스케줄러와 동일 락; 상세 NFR Design)
- **거래**: `Decision(source="human")` 구성 → `DecisionExecutor` 경유 RiskManager→Broker 실행 →
  종목 HumanLock 생성 → `InterventionRecord(outcome=...)` → async reconcile 트리거.
- **lifecycle**: `RunState` 갱신 → 로그.
- **approval**:
  - `/approve <id>`: `PendingApproval.decision` 실행(게이트) → 락 해제 → 에이전트 피드백 기록 → reconcile.
  - `/reject <id>`: 미실행 → 락 카운트++/denied → 에이전트 피드백 기록.
- **`/cancel`,`/unlock`,`/stop`**: 해당 브로커/락 연산 수행 → 로그.

### 3.3 에이전트 결정 경로 변경 (executor)
에이전트가 쓴 `Decision(source="agent")`을 executor가 처리할 때:
```
종목 락 상태?
 ├ locked  & 동작∈{BUY,SELL}        ─> PendingApproval 생성, 실행 보류, 콘솔 알림 한 줄
 ├ denied  & 동작∈{BUY,SELL}        ─> 자동 거부 + 에이전트 피드백(저널), 실행 안 함
 ├ 보호주문(ADJUST_STOP/HOLD+stop)  ─> 즉시 실행(락 예외)
 └ 락 없음                           ─> 기존대로 즉시 실행
```
- resting 보호 체결 / `run_risk_exits()`(폴드 청산)는 항상 동작(안전, 게이트 무관).

### 3.4 reconcile(재정렬) 흐름 (async, Q7=A)
- 트리거: 사람 **거래/directive**, 그리고 approve/reject로 장부가 바뀐 직후.
- 실행: 백그라운드 워커에서, 예약 턴과 **turn-lock 공유**(동시 `claude` 세션 충돌 방지, NFR-1).
- 입력 맥락: 직전 reconcile 이후의 사람 개입, 현재 보유, 락/denied/pending 상태, "장부를 현실에 맞추고
  사람 의도를 인지하라"는 지시.
- 디바운스: 짧은 시간 다수 개입은 1회로 합침.
- best-effort: 실패는 로그만, 데몬 비중단(기존 `_launch` try/except와 동일 정책).

## 4. 에이전트 피드백(승인 결과 전달) — "무한 재시도 방지"
승인/거부 결과는 에이전트가 다음 턴/리콘사일에서 읽도록 기록한다:
- 위치: `InterventionRecord(kind="approval")` + 에이전트 저널 노출(프롬프트 맥락).
- 내용 예: "너의 BUY AAPL 결정은 사람이 거부함(사유: …). 이 종목은 오늘 사람-락 상태." /
  "2회 거부되어 오늘은 더 제안 불가(denied)." / "사람이 승인하여 실행됨, 락 해제."
- 목적: 에이전트가 "왜 안 됐는지" 이해하고 같은 시도를 반복하지 않게.
