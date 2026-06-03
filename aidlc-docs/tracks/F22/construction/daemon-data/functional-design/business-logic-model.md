# Business Logic Model — Unit A: daemon-data

## BLM-1: 턴 ID 생성

### 위치: `src/agent/turn_log.py`

```
함수: generate_turn_id(path: Path, turn_type: str) -> str
  1. turns.jsonl에서 오늘 날짜 레코드 로드 (read_turns 재사용)
  2. 타입 접두사 매핑: research→R, intraday→I, wake→W, eod→E, reconcile→C
  3. 오늘 해당 타입의 기존 turn_id들에서 최대 번호 추출
  4. 번호 + 1 → "{접두사}{번호}" 반환
  5. 첫 턴이면 → "{접두사}1"
```

- **단일 프로세스 보장**: daemon은 `turn_lock`으로 동시 턴 불가 → 카운터 레이스 없음
- **날짜 리셋**: 오늘 날짜의 레코드만 필터링하므로 자동 리셋
- **ET 날짜 기준**: `date` 필드는 이미 로컬 타임(ET) 기준으로 기록됨

### 호출 지점: `record_turn()` 내부

기존 `record_turn()`에서 턴 기록 직전에 `generate_turn_id()`를 호출하여
`turn_id` 필드를 레코드에 포함. `record_turn()`의 반환값에도 `turn_id` 포함.

## BLM-2: 턴 요약 자동 생성

### 위치: `src/agent/turn_log.py`

```
함수: build_turn_summary(turn_type: str, decisions: list[Decision]) -> str
  1. 타입 레이블 매핑: research→"Research", intraday→"Intraday", wake→"Wake",
     eod→"EOD review", reconcile→"Reconcile"
  2. decisions가 비어있으면 → "{레이블}: no decisions"
  3. decisions[:4]를 순회하여 "{ACTION} {SYMBOL}({confidence})" 조합
  4. len(decisions) > 4이면 → "+{N} more" 추가
  5. 반환: "{레이블}: {조합된 결정 문자열}"
```

- 입력: 턴 타입 + 해당 턴에서 생성된 결정 목록
- 결정 목록은 오케스트레이터가 턴 실행 후 파악 가능 (반환된 Decision들)

### 호출 지점: `record_turn()` 호출 시

오케스트레이터가 `record_turn()`을 호출할 때 `decisions` 파라미터를 전달.
`record_turn()`이 `build_turn_summary()`를 호출하여 `summary` 필드 생성.

## BLM-3: Decision에 turn_id 전파

### 흐름

```
orchestrator.run_research/run_intraday/run_eod/run_wake()
  └── claude -p 실행 → decisions 파싱
      └── 각 Decision에 turn_id 세팅 (아직 turns.jsonl 기록 전)
          └── journal.append_decision(decision)  ← turn_id 포함
      └── record_turn(..., decisions=decisions)  ← turn_id 포함 레코드 기록
```

**문제**: 턴 ID는 `record_turn()` 시점에 생성되지만, decisions는 그 전에 journal에 기록됨.

**해결**: 턴 시작 시 `generate_turn_id()`를 호출하여 ID를 미리 확보.
오케스트레이터가 턴 시작 시 ID를 생성하고, 이를 decisions와 turn record 모두에 전달.

```
orchestrator.run_*(...)
  1. turn_id = generate_turn_id(journal.root / "turns.jsonl", turn_type)
  2. claude -p 실행 → raw decisions 파싱
  3. 각 decision.turn_id = turn_id
  4. journal.append_decision(decision)  # turn_id 포함
  5. record_turn(path, turn_type=..., turn_id=turn_id, decisions=decisions)
```

- `record_turn()`은 이제 `turn_id`를 인자로 받음 (내부 생성이 아닌 외부 전달)
- 이렇게 하면 ID가 기록 순서와 무관하게 일관됨

## BLM-4: monitor.json 확장

### 위치: `src/agent/steering/runtime.py`

#### `_turns_summary()` 수정

기존: 문자열 배열 반환
신규: `MonitorTurnEntry` 딕셔너리 배열 반환

```
함수: _turns_summary(path: Path) -> dict
  기존 today_count, today_cost_usd 유지
  recent: 마지막 8개 턴을 MonitorTurnEntry 객체로 변환
    - id: rec["turn_id"]
    - type: rec["turn_type"]
    - ts: HH:MM 형식
    - cost_usd: round(cost, 4)
    - num_decisions: rec["num_decisions"]
    - duration_ms: rec.get("duration_ms")
    - summary: rec["summary"]
    - health: "ok" (기본) / "error" (num_decisions=0 and turn_type in research,eod)
  반환: {"today_count": N, "today_cost_usd": X, "recent": [...]}
```

#### `_decisions_tail()` 수정

기존: 문자열 배열 반환
신규: `MonitorDecisionEntry` 딕셔너리 배열 반환

```
함수: _decisions_tail(path: Path) -> list[dict]
  마지막 10개 결정을 MonitorDecisionEntry 객체로 변환
    - turn_id: d.get("turn_id")
    - ts: HH:MM 형식
    - symbol: d["symbol"]
    - action: d["action"]
    - confidence: d.get("confidence")
    - reason: d.get("reason", "")[:60]
    - source: d.get("source", "agent")
  반환: [...]
```

#### 기존 문자열 소비자 수정

- `steer_read turns` / `steer_read decisions` (TypeScript 콘솔 핸들러):
  Unit B에서 구조화된 객체를 소비하도록 수정
- daemon 내부에서 monitor.json을 문자열로 읽는 곳이 있으면 함께 수정
  (실제로 daemon은 쓰기만 하고 읽지 않으므로 영향 없음)

## BLM-5: 진행 중 턴 표시 (in_progress health)

TUI가 "지금 턴 진행 중" 상태를 보여주려면 daemon이 턴 시작/종료를 알려야 한다.

### 접근법: monitor.json에 `current_turn` 필드 추가

```
monitor.json에 추가:
  "current_turn": {
    "id": "I3",
    "type": "intraday",
    "started_at": "10:31",
  } | null
```

- 턴 시작 시: `SteeringRuntime.set_current_turn(turn_id, turn_type)`
- 턴 종료 시: `SteeringRuntime.clear_current_turn()`
- `publish_monitor()`가 이 값을 payload에 포함
- `null`이면 현재 진행 중인 턴 없음

### 호출 지점

오케스트레이터가 턴 시작/종료 시 `steering.runtime`에 알림:
```
run_*(...)
  1. turn_id = generate_turn_id(...)
  2. runtime.set_current_turn(turn_id, turn_type)
  3. try:
       claude -p 실행 ...
     finally:
       runtime.clear_current_turn()
  4. record_turn(...)
```

- `finally` 블록으로 예외 시에도 반드시 클리어 (SECURITY-15: fail-safe)
