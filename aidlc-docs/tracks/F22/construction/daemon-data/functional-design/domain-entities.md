# Domain Entities — Unit A: daemon-data

## E1: TurnRecord (확장)

기존 `turn_log.record_turn()`이 생성하는 레코드에 `turn_id` 필드를 추가.

| 필드 | 타입 | 신규 | 설명 |
|------|------|------|------|
| `turn_id` | `str` | **NEW** | 타입 접두사 + 날짜 내 순차 (예: `R1`, `I3`, `W1`, `E1`, `C2`). 매일 리셋 |
| `ts` | `str` | — | ISO 8601 턴 완료 시각 |
| `date` | `str` | — | ISO date |
| `turn_type` | `str` | — | `research` / `intraday` / `eod` / `wake` / `reconcile` |
| `model` | `str` | — | Claude 모델 ID |
| `num_decisions` | `int` | — | 결정 수 |
| `cost_usd` | `float?` | — | LLM 비용 |
| `duration_ms` | `int?` | — | 소요 시간 |
| `num_turns` | `int?` | — | 내부 LLM 턴 수 |
| `input_tokens` | `int?` | — | 프롬프트 토큰 |
| `output_tokens` | `int?` | — | 완성 토큰 |
| `summary` | `str` | **NEW** | 결정 기반 자동 요약 1줄 |

### Turn ID 형식 (Q1=C)

- 접두사: `R`(research), `I`(intraday), `W`(wake), `E`(eod), `C`(reconcile)
- 카운터: 타입별 독립, ET 거래일 단위 리셋
- 예: 하루 중 `R1` → `I1` → `I2` → `W1` → `I3` → `E1`
- 생성: `turn_log.py`에서 기존 turns.jsonl을 읽어 오늘 해당 타입의 마지막 번호 + 1
- 충돌 방지: 단일 프로세스(daemon), 단일 turn_lock → 동시 생성 불가

### Turn Summary 형식 (Q3=A)

결정 기반 자동 조합:
- 결정 있을 때: `"{Type}: {ACTION1} {SYM1}({conf}), {ACTION2} {SYM2}({conf})"` (최대 4개, 초과 시 `+N more`)
- 결정 없을 때: `"{Type}: no decisions"`
- 예시:
  - `"Research: BUY AAPL(0.8), BUY MSFT(0.6), HOLD GOOGL(0.5)"`
  - `"Intraday: ADJUST_STOP AAPL(0.9)"`
  - `"Wake: no decisions"`

## E2: Decision (확장)

기존 `journal.Decision` pydantic 모델에 `turn_id` 필드 추가.

| 필드 | 타입 | 신규 | 설명 |
|------|------|------|------|
| `turn_id` | `str?` | **NEW** | 이 결정을 생성한 턴의 ID. 기존 결정(마이그레이션 전)은 `None` |
| `ts` | `datetime` | — | 결정 시각 |
| `symbol` | `str` | — | 종목 |
| `action` | `Literal` | — | BUY/SELL/HOLD/ADJUST_STOP |
| `source` | `Literal` | — | agent/human |
| `confidence` | `float?` | — | 신뢰도 0-1 |
| ... (기존 필드 유지) | | | |

- `turn_id`는 `Optional[str] = None`으로 추가 → 하위호환
- 사람(human) 결정은 `turn_id = None` (턴 밖에서 생성)

## E3: MonitorTurnEntry (신규)

`monitor.json`의 `turns.recent` 항목. 기존 문자열을 대체하는 구조화된 객체 (Q2=A).

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `str` | 턴 ID (E1.turn_id) |
| `type` | `str` | research/intraday/wake/eod/reconcile |
| `ts` | `str` | HH:MM 형식 시각 |
| `cost_usd` | `float` | LLM 비용 |
| `num_decisions` | `int` | 결정 수 |
| `duration_ms` | `int?` | 소요 시간 |
| `summary` | `str` | 결정 기반 자동 요약 |
| `health` | `str` | `ok` / `error` / `in_progress` |

## E4: MonitorDecisionEntry (신규)

`monitor.json`의 `decisions` 항목. 기존 문자열을 대체하는 구조화된 객체 (Q2=A).

| 필드 | 타입 | 설명 |
|------|------|------|
| `turn_id` | `str?` | 이 결정을 생성한 턴 ID |
| `ts` | `str` | HH:MM 형식 시각 |
| `symbol` | `str` | 종목 |
| `action` | `str` | BUY/SELL/HOLD/ADJUST_STOP |
| `confidence` | `float?` | 신뢰도 |
| `reason` | `str` | 이유 스니펫 (60자 truncate) |
| `source` | `str` | agent/human |
