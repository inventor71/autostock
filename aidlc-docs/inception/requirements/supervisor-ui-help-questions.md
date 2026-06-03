# F28 — Normal-mode UI 설명 요구사항 확인 질문

> `[Answer]:` 태그 뒤에 답을 적어주세요. A/B/C/D 중 선택 또는 `X) Other`.
> (이 트랙은 F26 "supervisor mode"와 별개 — F28은 "에이전트가 자기 UI를 설명하는 지식"을 다룬다.)

## 배경 (코드 확인)

- 사용자가 타임라인 topbar의 `$6.01`처럼 **화면 요소**를 물으면, 에이전트는 daemon snapshot/`steer_read`에 그 값이 없어 "모른다"고 답한다(스크린샷). 에이전트는 **자기 TUI가 무엇을 그리는지** 모른다.
- `$6.01` 추정: 타임라인 topbar 코드는 **F25 브랜치(active, 서브모듈 main 미포함)**에만 있어 직접 확인은 F28 discovery에서. 단 monitor.json `today_cost_usd`(runtime.py:381 `_turns_summary` = 오늘 턴들의 LLM 비용 합)일 가능성이 큼.
- normal mode(F26)는 코드 read 차단 + `$STEERING_DIR/**`만 read. 따라서 "코드를 읽어 설명"은 supervisor에서만 가능 — normal에서 답하려면 **코드 아닌 별도 지식원**이 필요.

---

## Question 1: 트랙으로 분리 (권장) vs F26의 유닛
A) **별도 트랙 F28 (권장)** — F26은 권한 레이어(설계 승인·단일 응집), 이건 지식 제공이라 도메인이 다름. F26의 `$STEERING_DIR/**` allowlist에 올라타 F26 설계를 안 건드림. 독립 머지 가능.
B) F26의 2번째 유닛으로 편입 — 승인된 F26 설계를 다시 열고 multi-unit로.
X) Other

[Answer]: A. 이미 분리되고 F26은 구현/머지됨.

---

## Question 2: 지식 전달 방식 (핵심 설계 분기)
에이전트가 UI 의미를 normal mode에서 얻는 경로는?

A) **steering 내 UI 사전 파일** — 예 `$STEERING_DIR/ui-reference.md`(또는 .json). 각 요소→의미(+데이터 출처) 기술. normal allowlist로 그대로 읽힘(F26 의존). 사람이 유지·간단. (단 코드와 drift 가능)
B) **데몬/TUI가 자동 발행** — 렌더링 코드/값에서 UI legend를 생성해 steering에 publish(snapshot/monitor처럼). 코드와 동기화 유지. (구현량↑)
C) **에이전트 system-prompt에 UI legend 주입** — 항상 컨텍스트에 존재(파일 read 불필요, F26 비의존). (매 턴 토큰 비용)
D) **신규 MCP read 뷰** — 예 `autostock_steer_read{view:ui_legend}`가 legend 반환(F26 비의존, MCP는 normal에서 허용).
X) Other

[Answer]: D. 근데 어떻게 구현하겠다는건지 감이 안옴. 코드와 계속 drift안하도록 어떻게 설계하지?

---

## Question 2a: Legend 데이터 원천 (drift 방지 핵심)
MCP가 반환할 UI legend는 어디서 오는가?

A) **TUI가 startup 시 자동 생성·기록** — TUI(오픈코드 fork)가 기동할 때 자신의 컴포넌트에서 legend JSON을 조립해 `$STEERING_DIR/ui-legend.json`에 쓴다. daemon은 이 파일을 읽어 MCP로 서빙만 한다. TUI 코드 = 원천, 항상 실행 중인 버전과 동기화. (단, normal-mode에선 TUI가 legend를 쓰고 에이전트가 읽는 타이밍 문제 — TUI가 켜져 있어야 legend 존재)
B) **빌드타임 추출** — TUI 빌드 스크립트(`bun run build` 등)가 컴포넌트 주석/태그에서 legend를 추출해 `steering/ui-legend.json`으로 출력. 버전 관리 가능, TUI가 안 켜져도 legend 있음. (단, TUI 빌드 파이프라인 수정 필요)
C) **정적 파일 (사람 유지)** — `$STEERING_DIR/ui-reference.md`를 사람이 작성·관리. 구현 가장 단순. (drift 위험 — TUI 변경 시 수동 업데이트 필요)
D) **하이브리드: TUI startup 생성 + 정적 fallback** — TUI가 legend를 생성해 쓰고, TUI가 없으면 마지막으로 쓴 파일을 daemon이 그대로 서빙. A의 장점 + TUI-off 대비.
X) Other

[Answer]: D

---

## Question 2b: MCP 도구 설계
어떤 MCP 도구로 legend를 제공할까?

A) **기존 `autostock_steer_read` 확장** — `autostock_steer_read{view:"ui_legend"}`가 legend를 반환. 도구 수 최소화, F26 allowlist 그대로.
B) **신규 전용 도구** — `autostock_ui_legend` 또는 `autostock_help_ui`. 의미가 명확하고 독립적. (F26 allowlist에 추가 필요 — but normal profile은 MCP tool 자체는 다 visible)
C) **steer_read + live 값 조합** — `steer_read{view:"ui_legend", element:"topbar.$"}` 하면 의미+현재 값(map된 snapshot 필드)까지 한 번에 반환. Q3=A(의미+값) 지원.
X) Other

[Answer]: C

---

## Question 2c: Legend 구조
UI legend의 데이터 형식은?

A) **단순 Markdown** — `ui-reference.md` 한 파일에 사람이 읽을 수 있는 설명. 에이전트가 Read로 읽음. 구현 가장 단순.
B) **구조화된 JSON** — 요소별 `{id, location, meaning, data_source(snapshot_field)}` 객체 배열. Q3=A(의미+값)의 data_source 매핑 가능, 에이전트가 필요한 요소만 쿼리 가능.
C) **Markdown + JSON 메타데이터 병행** — 사람용 .md + 기계용 .json. 양쪽 장점.
X) Other

[Answer]: B

---

## Question 3: 정적 의미만 vs 의미 + 현재 값
`$6.01` 질문에 어디까지 답하면 되나?

A) **의미 + 현재 값** (권장) — "타임라인 옆 `$X`는 **오늘 에이전트 턴 비용 합계**(today_cost_usd)이고, 지금 값은 $6.01" 처럼. legend가 UI요소→monitor/snapshot 필드로 매핑되어 에이전트가 실시간 값까지 설명.
B) **정적 의미만** — "그건 오늘 턴 비용 합계야"까지만. 실시간 수치는 사용자가 화면에서 보는 것으로 충분.
X) Other

[Answer]: A 

---

## Question 4: 커버리지 범위
지식 사전이 다룰 UI 범위는?

A) **전체 TUI** (권장) — topbar/타임라인(날짜 네비 `[< >]`, `$` 값, 마커 ◆/○/+/⧫), 사이드바(account/positions/round-trip/recent fills), 상태줄(RUNNING·MKT) 등 보이는 요소 전부.
B) **타임라인/topbar만** — 우선 이 영역만, 나머지는 후속.
X) Other

[Answer]: A

---

## Question 5 (보안 확장 opt-in)
Should security extension rules be enforced for this project?
A) Yes — enforce all SECURITY rules as blocking constraints
B) No — skip (이 트랙은 읽기 전용 UI 사전 제공이라 위험 표면이 작음)
X) Other

[Answer]: B

---

## Question 6 (속성 기반 테스트 확장 opt-in)
Should property-based testing (PBT) rules be enforced?
A) Yes  B) Partial  C) No (UI 사전/문서 위주 — C 무난)
X) Other

[Answer]: C
