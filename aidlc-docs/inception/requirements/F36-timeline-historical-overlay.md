# F36 — 타임라인 과거 마커 오버레이 버그 (Requirements)

> Track F36 · brownfield bug fix · `operator-console/cli` (TUI, F35 이후 monorepo 내 일반 디렉터리). 깊이: minimal/standard.
> Single source of truth = 트랙 `tracks/F36/state.md`·`audit.md`. 본 문서는 요구사항 산출물.

## 1. 문제 (Observed)
F25 히스토리 타임라인에서 **과거 ET 날짜**(예: 2026-06-02)의 turn 마커를 클릭하면 오버레이에
**"Turn W13 not found"** 가 뜬다(스크린샷). 과거 개입(human intervention) 마커는 클릭해도
**조용히 아무 반응이 없다**.

## 2. 근본 원인 (Root cause — 코드 대조 확정)
타임라인 마커와 상세 오버레이가 **서로 다른 데이터 소스**를 본다:
- **마커**: 선택된 날짜 세션 → `readSessionData(monitor, selectedDate)` 가 `turns.jsonl` /
  `human_directives.jsonl` 을 읽어 et_date로 필터 (`timeline-bar.tsx:44`).
- **turn 오버레이**: 라이브 payload `props.monitor.turns.recent` 만 조회 (`turn-overlay.tsx:19`)
  → 과거 turn id 부재 → "not found".
- **개입 오버레이**: 부모 라우트가 `monitor().interventions` 에서 재조회 (`index.tsx:1153`)
  → 과거 개입 부재 → 무응답.

핵심 비대칭: 개입은 이미 `openIntervention(iv, …)` 로 **전체 객체**를 오버레이 state에 저장하고
거기서 렌더한다(InterventionOverlay는 라이브 조회를 안 함). 반면 turn은 `openTurn(turnId, …)` 로
**id만** 저장 → 오버레이가 라이브 monitor를 재조회 → 버그. 개입 버그는 부모(`index.tsx:1153`)가
state에 넣기 전에 라이브에서 한 번 더 찾는 그 한 줄 때문.

## 3. 요구사항
- **FR-1**: 과거 날짜 turn 마커 클릭 시 해당 turn 상세가 **오늘 세션과 동일하게** 표시된다 —
  헤더(id/type/ts/duration/cost/dec) + 요약 + **결정 목록**(symbol/action/confidence/reason).
  ("not found" 제거.) [Q1=완전 동등]
- **FR-2**: 과거 날짜 개입(human) 마커 클릭 시 개입 오버레이가 정상적으로 열린다. [Q2=함께 수정]
- **FR-3**: 라이브(오늘) 세션의 turn/개입 오버레이 동작은 **회귀 없이** 동일하게 유지된다.
- **FR-4**: 과거 turn의 결정 상세는 `decisions.jsonl`(turn_id/et_date 없음)에서 복원한다 —
  et_date 필터 후 `ts`를 turn의 `[started_at, ts]` 시간창에 상관시켜 turn_id 부여.
  Python `src/agent/steering/runtime.py:755 _correlate_turn` 과 **동일 의미**(decision ts 이전에
  시작된 가장 최근 turn)로 TS 재현.

## 4. 설계 (단일 소스화 — 기존 개입 패턴에 맞춤)
오버레이가 **타임라인이 이미 해석한 선택-날짜 세션 객체**에서 렌더하도록 한다. turn 경로를
개입 경로와 대칭으로 만든다: **전체 turn 객체 + 그 turn의 결정 배열**을 오버레이 state에 전달.

- `use-session-data.ts`: `SessionData` 에 `decisions: MonitorDecision[]` 추가.
  - live 분기: `monitor.decisions ?? []` (이미 turn_id 보유).
  - historical 분기: `decisions.jsonl` 읽어 et_date 필터 → `correlateTurnId(ts, turnIdx)` 로
    turn_id 부여 → `MonitorDecision` 매핑. `turnIdx` 는 그 날짜 turns의 `(started_at, ts, id)`.
- `use-overlay.ts`: `OverlayState` 에 `turn: MonitorTurn|null`, `decisions: MonitorDecision[]`
  추가. `openTurn(turn, decisions, x, y)` 가 객체 저장(토글 비교 `cur.turn?.id === turn.id`).
- `turn-overlay.tsx`: props `monitor` 제거 → `turn: MonitorTurn` + `decisions: MonitorDecision[]`.
  `turn()=props.turn`, `decisions()=props.decisions`. (방어적 fallback은 유지.)
- `timeline-bar.tsx`: `session()` 에 decisions 포함. `onMarkerClick(turn, decisions, x, y)` 로
  시그니처 변경; MarkerRow + F34 라벨셀 클릭 경로 둘 다 `mp.turn` 과
  `session().decisions.filter(turn_id===mp.turn.id)` 전달. `onInterventionClick(iv, x, y)` 로
  **전체 객체** 전달(라벨셀 경로 포함).
- `index.tsx`: `onMarkerClick={(turn,dec,x,y)=>overlay.openTurn(turn,dec,x,y)}`;
  `onInterventionClick={(iv,x,y)=>overlay.openIntervention(iv,x,y)}` (라이브 재조회 삭제);
  TurnOverlay 마운트를 `turn`/`decisions` props 로 교체, `Show when=…overlay.state().turn`.
- **범위 밖**: 심볼 오버레이(`index.tsx:1346`, 별개 기능), 데몬/Python 발행 경로(불변).

## 5. 검증 포인트 (구현 시 확인)
- `turns.jsonl.started_at` 와 `decisions.jsonl.ts` 의 ISO 포맷/타임존이 **문자열 사전순 비교**로
  안전한지(=_correlate_turn 과 동일 전제). 다르면 Date.parse 기반 비교로 보강.
- 과거 날짜에서 turn↔decision 상관 정확도(개수 일치: 헤더 `num_decisions` vs 표시 건수 근접).
- 오늘 세션 회귀: turn/개입 오버레이 토글·내용 동일.

## 6. Extensions
- Security Baseline: 대부분 N/A. 읽기 전용 파일 접근(기존 `readJsonl` 재사용), 신규 비밀/네트워크
  표면 없음. SECURITY-03(로그 마스킹)·15는 본 변경과 무관(N/A).
- PBT: N/A (버그 픽스; 상관 로직에 타깃 유닛 테스트로 충분).

## 7. 단위(Units) / 단계
단일 유닛 `timeline-historical-overlay-fix`. User Stories SKIP · Application Design SKIP(배선 변경)
· Units Generation SKIP · Infra Design SKIP. Functional/NFR Design 경량(본 문서로 갈음) →
Code Generation → Build & Test.
