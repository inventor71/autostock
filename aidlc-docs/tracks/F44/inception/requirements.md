# F44 요구사항 — 진행 중 turn 라벨(TUI) + 동일 type turn dedup(daemon)

> 깊이: **standard**. Brownfield, 기존 컴포넌트 경계 내 변경. 운영자 1인.
> 관련 메모: [[steering-console-redesign]] [[f4-steering-runtime-wiring]] (F38 manual turn, F41 current_turn/overlay).

## 1. 배경 / 문제
- 운영자가 `/research`로 수동 research turn을 트리거할 때, **이미 turn이 진행 중이면**
  무엇이 몇 분째 돌고 있는지 화면에서 확인할 방법이 약하다. 현재 신호는 타임라인
  now-cursor(`▼`/`┃`)가 **초록 점멸**하는 것뿐(`timeline-bar.tsx:174,238`) — 종류/경과 텍스트 없음.
- 또한 수동 트리거는 **무조건 큐잉**된다(`_v_research` → `turn_trigger_fn("research")` →
  `coordinator.start_priority_async`). 동일 type을 두 번 누르면 **둘 다 큐에 쌓인다**
  (이번 세션 실측: 자동 premarket research R1 실행 중 + 수동 `/research` 2회가 전부 큐잉).

## 2. 범위 (2개 독립 기능)
### 기능 A — 진행 라벨 (TUI, tui-trading)
- 데이터는 이미 `monitor.json` `current_turn = {id, type, started_at}`에 존재 → 재사용.
- **위치**: TimelineBar 상단 전폭 **상태줄** 한 줄(now-cursor와 같은 영역).
- **내용**: `● {type} · {elapsed} · +{N} queued`
  - `type`: research / intraday / eod 등 current_turn.type
  - `elapsed`: `started_at` 기준 경과(틱마다 갱신; 예 `3m12s`). 1초 미만/유휴 처리.
  - `+{N} queued`: 대기 중인 turn 수(0이면 ` · +N queued` 생략).
- **유휴 상태**(current_turn 없음): 상태줄을 비우거나 `idle`로 표기(점멸 색상 기존 동작 유지).
- 라이브 세션에서만 표시(과거 날짜 선택 시 미표시) — now-cursor와 동일 정책.

### 기능 B — 동일 type turn dedup (daemon, Python)
- 수동 트리거(`_v_research` 경로)에서 요청 type이 **현재 실행 중**이거나 **이미 대기열에 있으면**
  큐에 넣지 않고 즉시 반환.
- "running" 판정: `runtime._current_turn.type == 요청 type` (자동/수동 turn 모두 커버 —
  scheduled 포함 모든 turn이 `_on_turn_start`→`set_current_turn`을 거침).
- "queued" 판정: coordinator가 추적하는 대기 중 manual turn kind 집합에 요청 type 존재.
- 반환/표시: 운영자에게 별도 outcome으로 보고
  - 실행 중: `already_running` → 예) `"research already in progress (running 3m12s) — not queued"`
  - 대기 중: `already_queued` → 예) `"research already queued — not re-queued"`
- 원자성: 검사+enqueue는 coordinator의 `_waiters_lock` 하에서 원자적으로 수행
  (CommandBus 단일 워커라 명령은 순차 처리되지만, 락으로 불변식을 코드 레벨에서 보장).

## 3. 기능 요구사항 (FR)
- **FR-A1**: turn이 in-flight인 동안 상태줄에 `● {type} · {elapsed}`를 표시한다.
- **FR-A2**: 대기 turn이 있으면 ` · +{N} queued`를 덧붙인다(N=0이면 생략).
- **FR-A3**: 유휴 시 상태줄은 비거나 `idle`; 과거 날짜 선택 시 표시하지 않는다.
- **FR-A4**: elapsed는 표시 동안 주기적으로 갱신된다(기존 blink 타이머 재사용 가능).
- **FR-B1**: 동일 type이 실행 중이면 `already_running`을 반환하고 큐잉하지 않는다.
- **FR-B2**: 동일 type이 이미 대기열에 있으면 `already_queued`를 반환하고 큐잉하지 않는다.
- **FR-B3**: 서로 다른 type은 기존대로 큐잉/실행된다(차단하지 않음).
- **FR-B4**: dedup 검사+enqueue는 원자적이어야 한다(동일 type 2개가 동시에 큐/실행 진입 불가).
- **FR-B5**: 대기열 수(또는 대기 kind 목록)를 monitor.json에 발행해 기능 A의 `+N queued`를 뒷받침.

## 4. 비기능 / 제약 (NFR)
- **NFR-1 (불변)**: `claude --resume` 동시 2개 금지 — 기존 turn_lock 직렬화 유지. dedup은
  큐잉 억제일 뿐 락 의미를 바꾸지 않는다.
- **NFR-2**: dedup 추가가 scheduled/reconcile/wake 우선순위(F38) 동작을 회귀시키지 않아야 한다.
- **NFR-3**: TUI 라벨 렌더는 파일(monitor.json)만 읽고 브로커/네트워크 접근 없음(기존 정책).
- **NFR-4**: 모든 변경은 best-effort — dedup/라벨 실패가 turn 실행 자체를 깨뜨리면 안 됨(BR-6.3).

## 5. Extension Configuration (이 트랙)
- **Property-Based Testing**: **Enabled** — Unit1 dedup 동시성/상태전이 불변식 검증
  (무작위 트리거 시퀀스에 대해 "동일 type 동시 2개 큐/실행 안 됨").
- **Security Baseline**: **Disabled** — 신규 외부 표면/시크릿 처리 없음(라벨은 turn type/시간만,
  기존 maskSecrets 경로 무관). 대부분 규칙 N/A.

## 6. 영향 파일 (예상)
- daemon: `src/agent/steering/turns.py`(coordinator dedup + 대기 kind 추적),
  `src/agent/steering/runtime.py`(`_trigger_turn` dedup 판정 + monitor 발행),
  `src/agent/steering/commands.py`(`_v_research` already_running/already_queued outcome).
- TUI: `operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx`(상태줄),
  `.../hooks/use-monitor-data.ts` + `.../types.ts`(queued 수 노출).
- tests: `tests/test_*`(dedup + property-based), `operator-console/cli/packages/tui-trading/test/*`.

## 7. 가정 / 비범위
- dedup은 **수동 트리거 경로**에만 적용(scheduled/wake/reconcile은 기존 skip/queue 정책 유지).
- 현재 수동 verb는 `/research`뿐이나, dedup은 **type 키 기반 일반화**로 구현(향후 intraday/eod
  수동 트리거가 생겨도 동작).
- 큐 우선순위/선점(preemption)은 변경하지 않는다(별도 관심사).
