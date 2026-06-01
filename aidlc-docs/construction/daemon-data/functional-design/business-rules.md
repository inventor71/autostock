# Business Rules — Unit A: daemon-data

## BR-1: 턴 ID 유일성

- 같은 ET 거래일 + 같은 타입 내에서 턴 ID는 유일해야 한다
- `generate_turn_id()`는 기존 turns.jsonl에서 오늘 해당 타입의 최대 번호를 읽고 +1
- 단일 프로세스 + turn_lock → 레이스 조건 구조적 불가

## BR-2: 턴 ID는 턴 시작 시 생성

- `generate_turn_id()`는 턴 실행 전에 호출 (BLM-3)
- 이유: decisions가 journal에 먼저 기록되므로, 결정에 turn_id를 달려면 미리 확보 필요
- 턴이 실패해도 ID는 소비됨 (번호 건너뜀 허용 — 연속성보다 유일성 우선)

## BR-3: Decision.turn_id는 Optional

- 기존 결정(마이그레이션 전)은 `turn_id = None`
- 사람(human source) 결정은 `turn_id = None` (턴 밖에서 생성)
- TUI는 `turn_id`가 없는 결정도 정상 표시 (턴 링크 없이)

## BR-4: monitor.json 구조 변경 (Q2=A)

- `turns.recent`: 문자열 배열 → `MonitorTurnEntry` 딕셔너리 배열
- `decisions`: 문자열 배열 → `MonitorDecisionEntry` 딕셔너리 배열
- 이전 포맷 유지 안 함 — 소비자(TypeScript 콘솔)를 Unit B에서 함께 수정
- `ts`, `log` 필드는 기존 형식 유지

## BR-5: 턴 요약은 결정론적 (Q3=A)

- LLM 호출 없이 결정 목록에서 자동 조합
- 결정 4개 초과 시 `+N more`로 축약
- 결정 0개 시 `"{Type}: no decisions"`
- confidence는 소수점 1자리로 표시

## BR-6: health 필드 결정 로직

| 조건 | health |
|------|--------|
| 턴 정상 완료 + 결정 ≥ 0 | `ok` |
| 턴 실행 중 (current_turn != null) | `in_progress` |
| 턴 예외/에러 발생 | `error` |

- `in_progress`는 `monitor.json`의 `current_turn` 필드로 표현 (recent 배열이 아님)
- `error`는 `record_turn()` 호출 시 에러 플래그 전달 (새 파라미터 `error: bool = False`)

## BR-7: current_turn fail-safe (SECURITY-15)

- `set_current_turn()`과 `clear_current_turn()`은 try/finally로 보호
- 예외 발생 시에도 `clear_current_turn()` 반드시 호출
- daemon 재시작 시 `current_turn`은 자동으로 `null` (인메모리, 비영속)

## BR-8: monitor.json 발행 주기 무변경

- `publish_monitor()`의 10초 주기 유지 (NFR-1, Q7=A)
- 구조화된 객체로 변경해도 직렬화 비용 무시 가능 (레코드 수 ≤ 10개)

## BR-9: 로깅에 민감정보 제외 (SECURITY-03)

- monitor.json의 `log` 필드: 기존 `_mask_secrets()` 유지
- turn_id, summary, decision 내용에 토큰/API키 포함 불가 (결정론적 생성이므로 구조적으로 안전)
- `current_turn`에 민감정보 없음 (id + type + ts만)

## BR-10: 기존 코드 영향 범위

### 수정 파일 (Python)
| 파일 | 변경 |
|------|------|
| `src/agent/turn_log.py` | `generate_turn_id()`, `build_turn_summary()` 추가; `record_turn()` 시그니처 확장 |
| `src/agent/journal.py` | `Decision` 모델에 `turn_id: str | None = None` 추가 |
| `src/agent/orchestrator.py` | 턴 시작 시 turn_id 생성, decisions에 전파, record_turn에 전달 |
| `src/agent/steering/runtime.py` | `_turns_summary()`, `_decisions_tail()` 구조화 객체 반환; `current_turn` 관리 |
| `src/trading/modes/agent.py` | `set_current_turn`/`clear_current_turn` 호출 추가 (오케스트레이터 래퍼에서) |

### 미수정 파일
| 파일 | 이유 |
|------|------|
| `src/agent/steering/channel.py` | snapshot.json 무변경 |
| `src/agent/steering/state.py` | 상태 관리 무변경 |
| `src/agent/steering/commands.py` | 커맨드 처리 무변경 |
| `src/agent/intraday/` | 인트라데이 시스템 무변경 (wake 턴도 오케스트레이터 경유) |
