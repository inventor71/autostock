# Functional Design Plan — ui-legend

> Track: F28 · Unit: `ui-legend` · Depth: Minimal
> Requirements: `aidlc-docs/inception/requirements/normal-ui-help.md`

## Plan Steps

- [x] Step 1: Analyze unit context (requirements → entities, rules, boundaries)
- [x] Step 2: Present 설계 질문 (Q-FD1 ~ Q-FD4) → 답변 수집
- [x] Step 3: Generate artifacts (`domain-entities.md`, `business-logic-model.md`, `business-rules.md`)
- [x] Step 3b: `/critic` #1 (3H+3M+1L) → 서빙=TS MCP 서버, command verb 그래머, JSON Pointer.
- [x] Step 3c: **범위 단순화** (사용자) — 정적 의미 사전만. data_source/현재값/TUI 자동생성/fallback 제거.
- [x] Step 3d: `/critic` #2 (2H+1M+1L, 전부 valid) → F29 codebase verb 선례 채택. mcp-server description MANDATORY, element는 handler가 raw에서 split, schema.ts 미변경, readFileSync(import 금지). 4문서 반영.
- [ ] Step 4: Present completion → 승인 요청 (critic#2 반영 후 재제시)

---

## 설계 질문

### Q-FD1: JSON 스키마 — 필수/선택 필드

`ui-legend.json` 각 항목의 필드는?

A) **`id`, `meaning`만 필수** (권장) — `location`, `data_source`는 선택. 단순. 에이전트는 id로 찾고 meaning으로 설명. data_source 없으면 정적 의미만.
B) **`id`, `location`, `meaning`, `data_source` 모두 필수** — 모든 요소가 위치·의미·데이터 출처를 가져야 함. 빠짐없이 완전한 설명.
C) **`id`, `meaning` 필수 + `aliases`(검색용 키워드 배열), `data_source` 선택** — 사용자가 "달러 표시" "비용" 등 다양한 표현으로 물을 수 있어 alias 검색 지원.
X) Other

[Answer]: A 

---

### Q-FD2: data_source 경로 표기법

snapshot/monitor JSON의 특정 필드를 가리키는 `data_source` 표기법은?

A) **Dot-notation** — `"monitor.turns.today_cost_usd"`. 읽기 쉽고 구현 단순. (snapshot 최상위 키로 구분: `monitor.*`, `snapshot.*`)
B) **JSON Pointer (RFC 6901)** — `"/monitor/turns/today_cost_usd"`. 표준. 중첩 객체에 강함.
C) **`{source, path}` 객체** — `{"source": "monitor", "path": "turns.today_cost_usd"}`. 명시적. 파싱 오류 적음.
X) Other

[Answer]: B

---

### Q-FD3: TUI legend 선언 방식

TUI(오픈코드 fork) 컴포넌트가 자신의 legend를 어떻게 선언하는가?

A) **컴포넌트 근처 상수 export** — 각 UI 컴포넌트 파일에서 `export const legend = {id, meaning, data_source}` 상수를 export. startup 시 import해서 수집. 코드와 가장 가까움.
B) **중앙 registry 파일** — `src/ui-legend.ts` 하나에 모든 legend 항목을 배열로. 한눈에 보기 좋으나 컴포넌트와 물리적으로 떨어짐.
C) **JSDoc/주석 태그** — `/** @legend id:"topbar.$" meaning:"오늘 턴 비용" */` 주석을 빌드타임에 추출. 코드에 가장 가볍게 붙음.
X) Other

[Answer]: A

---

### Q-FD4: 정적 fallback 위치

TUI가 off 상태일 때 사용할 정적 fallback `ui-legend.json`은 어디에 두는가?

A) **서브모듈에 커밋** (`operator-console/cli/assets/ui-legend.json`) — TUI의 일부로 버전 관리. TUI 배포와 함께 자연스럽게 업데이트.
B) **Parent repo의 steering 템플릿** (`steering/ui-legend.json`) — daemon과 같은 repo. 서브모듈 없이 daemon만으로 존재 가능.
C) **둘 다**: TUI가 생성한 것은 `$STEERING_DIR/`에, fallback은 서브모듈 assets에. daemon은 `$STEERING_DIR/` 먼저 보고 없으면 assets 경로 fallback.
X) Other

[Answer]: A

---

## 설계 범위 (질문 답변 후 생성할 아티팩트)

1. **domain-entities.md** — `UiLegendEntry`, `UiLegend` 스키마, `DataSourceRef` 타입
2. **business-logic-model.md** — legend 생성 흐름(TUI startup → write → MCP serve), data_source 해석 흐름
3. **business-rules.md** — 필수 필드 검증, data_source 경로 추적 규칙, fallback 우선순위, element 필터링 규칙
