# AI 협업 TUI 개선 — 요구사항 (F22)

## 1. Intent Analysis

- **User Request**: "AI (research/intraday)와 같이 거래하는게 특징인데 현재 TUI는 그거에 특화된 부분이 없어. 새로운 협업 방식 및 UI개선을 원해"
- **Request Type**: Enhancement (기존 TUI에 AI 협업 특화 UI 추가)
- **Scope**: Multiple Components — opencode 포크 TUI(TypeScript) + daemon MCP(Python) + 데이터 흐름 확장
- **Complexity**: Complex — 새로운 UI 패러다임(타임라인 바 + 호버 오버레이), 별도 패키지, daemon 데이터 소비
- **Depth**: Standard

## 2. 핵심 설계 컨셉

### 2.1 타임라인 바 + 호버 오버레이 패러다임

메인 채팅 영역 **상단에 상시 표시**되는 컴팩트한 타임라인 바. 각 턴이 마커로 표현되며,
마커의 형태/색상으로 턴 타입(research/intraday/wake/eod)과 상태(health)를 즉시 파악.

```
  09:30      10:00      10:30      11:00      11:30
  ──●────────◆────────○────────○────────▲──────→ now
  research   wake      intraday   intraday   eod
```

- **마커 위 호버** → 해당 턴의 **상세 오버레이** 팝업:
  - 턴 요약 (모델, 비용, 소요시간, 결정 수)
  - Decision Feed: 해당 턴에서 내린 결정들 (심볼, 액션, 신뢰도, 가격, 이유 스니펫)
  - 추론 요약 (Q4=A: 1-2문장 기본; 턴 ID로 상세 요청 가능)

- **심볼 위 호버** → 해당 심볼의 **논거(thesis) 오버레이** 팝업:
  - `positions/SYMBOL.md` 내용
  - 최근 결정 이력
  - 사이드바, 타임라인 오버레이, 채팅 등 어디서든 심볼에 호버하면 동작

### 2.2 두 가지 뷰 모드 (Q2=D 부분)

- **기본 모드**: 채팅 뷰 + 상단 타임라인 바 (상시)
- **대시보드 모드**: 단축키로 전환, 전체 턴 이력/결정/계정 상태를 한눈에 (향후 확장 여지)

v1에서는 **기본 모드의 타임라인 바 + 오버레이**에 집중. 대시보드 모드는 타임라인 바가
동작하면 자연스럽게 확장 가능.

## 3. Functional Requirements

### FR-1: 에이전트 턴 타임라인 바

- **FR-1.1**: 채팅 영역 상단에 가로 타임라인 바를 상시 표시
- **FR-1.2**: 오늘의 모든 턴(research, intraday, wake, eod, reconcile)을 시간 순서대로 마커로 배치
- **FR-1.3**: 마커 디자인 — 턴 타입별 고유 아이콘/형태 + 색상:
  - research: 별도 형태 (예: ●), 강조색
  - intraday: 기본 형태 (예: ○)
  - wake: 이벤트 트리거 형태 (예: ◆)
  - eod: 종료 형태 (예: ▲)
  - reconcile: 동기화 형태 (예: ↻)
- **FR-1.4**: 마커 상태(health) 표현 — 결정 유무, 성공/실패 등을 색상/장식으로 구분
  - 결정 있음 → 채워진 마커
  - 결정 없음(순수 모니터링) → 비어 있는 마커
  - 실패/에러 → 빨간 마커 (예: ✕)
- **FR-1.5**: 현재 시점 표시 (`→ now`) + 장이 열린/닫힌 시간대 구분
- **FR-1.6**: 타임라인 데이터 소스: `monitor.json`의 `turns.recent` 배열 (10초 주기 폴링, Q7=A)

### FR-2: 턴 마커 호버 오버레이

- **FR-2.1**: 마커 위에 마우스를 올리면 상세 정보 오버레이 팝업
- **FR-2.2**: 오버레이 내용:
  - **턴 메타**: 턴 ID, 타입, 시작 시각, 소요시간, 모델, 비용(USD), 토큰 수
  - **결정 목록**: 해당 턴에서 생성된 결정들 (심볼, 액션, 신뢰도, 제안 가격)
  - **추론 요약**: 1-2문장 요약 (Q4=A)
- **FR-2.3**: 오버레이 내 심볼은 클릭/호버 가능 → FR-4 심볼 오버레이 트리거
- **FR-2.4**: 오버레이는 마우스가 벗어나면 닫힘 (또는 클릭으로 핀 고정)

### FR-3: Decision Feed (결정 피드)

- **FR-3.1**: 턴 오버레이 내에서 해당 턴의 결정들을 리스트로 표시
- **FR-3.2**: 결정 항목별 표시 정보:
  - 심볼, 액션(BUY/SELL/HOLD/ADJUST_STOP), 신뢰도(0-1)
  - 제안 가격 (limit_price, stop_price, target_price)
  - 이유 스니펫 (짧은 설명)
  - 소스 태그 (agent/human)
- **FR-3.3**: 색상 코딩 — 액션별 시각 구분 (BUY=초록, SELL=빨강, HOLD=회색, ADJUST=노랑)
- **FR-3.4**: 데이터 소스: `monitor.json`의 `decisions` 배열

### FR-4: 심볼 호버 오버레이 (Thesis Viewer)

- **FR-4.1**: TUI 어디서든 심볼 텍스트(예: "AAPL") 위에 호버하면 해당 심볼의 논거 오버레이 팝업
- **FR-4.2**: 오버레이 내용:
  - `positions/SYMBOL.md`의 내용 (마크다운 렌더링)
  - 해당 심볼의 최근 결정 이력 (decisions에서 필터)
  - 현재 포지션 상태 (snapshot의 positions에서)
- **FR-4.3**: 작동 범위:
  - 사이드바의 심볼 표시
  - 타임라인 턴 오버레이 내 심볼
  - 채팅 메시지 내 심볼 (가능한 범위에서)
- **FR-4.4**: 오버레이는 마우스가 벗어나면 닫힘
- **FR-4.5**: 데이터 소스:
  - 논거: MCP 도구를 통해 `workspace/positions/SYMBOL.md` 읽기 (또는 daemon이 snapshot에 포함)
  - 포지션: `snapshot.json`의 `positions`
  - 결정: `monitor.json`의 `decisions`

### FR-5: 턴 고유 ID 및 상세 조회

- **FR-5.1**: 각 턴에 고유한 짧은 ID 부여 (예: `T1`, `T2`, ... 또는 `R1`, `I3`, `W1`, `E1` 타입 접두사)
- **FR-5.2**: 턴 ID로 상세 정보 조회 가능 — 대화형으로 "T3에 대해 알려줘" 같은 질문 시 상세 추론 과정 제공
- **FR-5.3**: 턴 ID는 타임라인 마커와 오버레이에 표시
- **FR-5.4**: daemon 측: `turns.jsonl`에 턴 ID 필드 추가 (또는 기존 인덱스 활용)
- **FR-5.5**: MCP 도구 확장: 턴 ID로 상세 조회하는 도구 (기존 `agent_trace.py` 로직 활용)

### FR-6: 데이터 흐름 (daemon → TUI)

- **FR-6.1**: 기존 데이터 채널 유지 — `snapshot.json`(5초), `monitor.json`(10초), `events.jsonl` (Q7=A)
- **FR-6.2**: `monitor.json` 확장:
  - `turns.recent` 항목에 턴 ID 추가
  - `turns.recent` 항목에 턴 요약(1-2문장) 추가 (현재: "09:43 wake $0.51 0dec" → 요약 필드 추가)
  - `decisions` 항목에 해당 턴 ID 링크 추가
- **FR-6.3**: 심볼 논거 접근: MCP 도구(`steer_read thesis SYMBOL`) 또는 `monitor.json` 확장
- **FR-6.4**: 타임라인 렌더링에 필요한 데이터:
  - 턴 목록: `[{id, type, start_time, duration_ms, model, cost_usd, num_decisions, health, summary}]`
  - 결정 목록: `[{turn_id, symbol, action, confidence, prices, reason_snippet}]`

## 4. Non-Functional Requirements

### NFR-1: 기존 인프라 무변경
- 폴링 주기 변경 없음 (snapshot 5초, monitor 10초)
- 새로운 IPC 채널이나 프로토콜 도입 없음
- daemon의 기존 CommandBus/SteeringRuntime 구조 유지

### NFR-2: 성능
- 타임라인 바 렌더링은 채팅 UI 응답성에 영향 없어야 함
- 오버레이 팝업은 호버 후 <200ms 이내 표시
- monitor.json 파싱은 10초 주기 안에서 완료

### NFR-3: 유지보수성
- 별도 패키지로 분리 (Q8=B) — 기존 opencode 코어와 독립
- 마커/오버레이 컴포넌트는 재사용 가능하도록 설계

### NFR-4: 접근성
- 타임라인 마커는 색상 외에 형태로도 구분 가능 (색약 대응)
- 키보드로 타임라인 탐색 가능 (Tab/화살표)

### NFR-5: 알림
- 별도 알림 없음 (Q6=A) — 타임라인 바가 상시 표시되므로 자연스럽게 인지

## 5. Technical Decisions

| 결정 | 선택 | 근거 |
|------|------|------|
| UI 위치 | 채팅 상단 타임라인 바 + 호버 오버레이 | Q2: 상시 가시성 + 공간 효율 |
| 추론 깊이 | 요약(기본) + 턴 ID 조회(상세) | Q4: 평소엔 가볍게, 필요 시 drill-down |
| v1 범위 | 전체 (A,B,D,E) | Q5=C: 포괄적 구현 |
| 폴링 주기 | 현행 유지 (5s/10s) | Q7=A: 이번 범위 밖 |
| 패키지 구조 | 별도 패키지 분리 | Q8=B: 구현량 고려 |
| 서브모듈 | feat/F22 브랜치 | Q9=A: concurrent-tracks 규칙 |
| daemon 변경 | monitor.json 확장 (턴 ID, 요약, 결정-턴 링크) | 최소 변경 원칙 |

## 6. 범위 밖 (Not in Scope)

- **Approval Queue UI** (Q1에서 C 미선택) — CLI 명령어로 충분
- **Directive 관리 UI** (Q3에서 B 미선택) — CLI 명령어로 충분
- **AI 질의응답 UI** (Q3에서 C 미선택)
- **Push 알림 / 외부 알림** (Q6=A)
- **폴링 주기 변경** (Q7=A) — 별도 트랙으로 미룸
- **대시보드 전용 뷰 모드** — v1 이후 확장

## 7. Extension Configuration

| Extension | Enabled | Mode | Applicable Rules |
|-----------|---------|------|------------------|
| Security Baseline | Yes (Q11=A) | Enforce, blocking | SECURITY-03 (로깅에 민감정보 제외), SECURITY-11 (보안 설계 원칙), SECURITY-15 (예외처리/fail-safe). 나머지 N/A (웹앱/DB/API/IaC 없음) |
| Property-Based Testing | Partial (Q12=B) | Pure functions + serialization round-trips | PBT-02, PBT-03, PBT-07, PBT-08, PBT-09. Hypothesis(Python), fast-check(TS 해당 시). 순수 함수만 |

## 8. 위험 요소

- **opencode 포크 호환성**: 상단에 타임라인 바를 추가하려면 메인 레이아웃 수정 필요. 포크 구조에 대한 이해 필요
- **호버 오버레이 구현**: Ink(터미널 React) 환경에서 마우스 호버 이벤트 처리의 제약 가능성
  - **대안**: 터미널이 마우스 호버를 지원하지 않는 경우, 키보드 네비게이션(좌/우 화살표로 턴 선택) + Enter로 오버레이 토글
- **심볼 오버레이 범위**: 채팅 메시지 내 심볼 감지는 텍스트 파싱이 필요하여 구현 복잡도 증가 가능
- **daemon monitor.json 확장**: 기존 포맷에 필드 추가 시 하위 호환성 유지 필요

## 9. 사용자 핵심 페인포인트 (Q10)

- **A: 블라인드 운영** — AI 턴 진행 중에는 무엇을 하는지 전혀 안 보임. 턴이 끝나야 결과 확인.
  → **해결**: 타임라인 바가 "지금 턴 진행 중" 상태를 실시간 표시 (진행 중 마커 = 깜빡임/애니메이션)
- **B: 맥락 부재** — 왜 이 종목을 샀는지, 왜 이 가격에 스톱을 걸었는지 TUI에서 바로 안 보임.
  → **해결**: 심볼 호버 오버레이로 즉시 논거 확인 + 턴 오버레이에서 결정 이유 스니펫 제공
