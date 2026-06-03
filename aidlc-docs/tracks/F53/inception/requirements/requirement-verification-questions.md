# F53 요구사항 확인 질문 — MCP Position Thesis 노출

아래 질문에 답변해 주세요. 각 질문의 `[Answer]:` 태그 뒤에 선택한 옵션의 알파벳을 적어주세요.
제공된 옵션 중 맞는 것이 없으면 마지막 `기타` 옵션을 선택하고 선호하는 내용을 설명해 주세요.

---

## Question 1: Thesis 데이터 노출 방식

에이전트가 `workspace/positions/<SYMBOL>.md`에 기록하는 포지션 테제를 TUI에서 확인할 수 있게 하는 가장 적절한 방법은 무엇인가요?

A) 새 `steer_read` 서브커맨드 (`/thesis <SYMBOL>`) — 데몬이 `workspace/positions/<SYMBOL>.md`를 읽어 내용을 반환. 기존 `steer_read /status`, `/turns` 등과 동일한 구조.
B) 새 독립 MCP 툴 `get_position_thesis` — MCP 서버(TypeScript)가 직접 `workspace/positions/<SYMBOL>.md` 파일을 읽어 반환. `get_all_positions` 같은 Alpaca read 툴과 유사한 패턴.
C) 기존 `steer_read /status` 응답(snapshot.json)에 thesis 요약(stop, target, thesis 한 줄)을 포함 — 포지션 조회 시 thesis 핵심 정보가 함께 표시됨.
D) 기존 `get_all_positions` 응답에 thesis 파일 경로/요약을 추가 + 별도 툴로 전문 조회 (A+B 조합)

[Answer]: A

---

## Question 2: 반환할 Thesis 데이터 형식

Thesis 데이터를 어떤 형식으로 반환해야 하나요?

A) Raw markdown 전문 — `workspace/positions/<SYMBOL>.md` 파일 내용을 그대로 텍스트로 반환
B) 파싱된 구조화 데이터 — Stop, Target, Thesis 요약, 마지막 Call 등을 JSON 구조로 반환 (데몬/서버에서 마크다운 파싱 필요)
C) A+B 혼합 — 기본은 구조화된 요약(Stop/Target/리스크:리워드/마지막 Call)을 반환하고, `/thesis <SYMBOL> --full`로 원본 마크다운 전문도 조회 가능

[Answer]: A. 대신 agent를 이를 전문으로, 혹은 요약해서 알려줄수 있음 

---

## Question 3: Thesis 파일 읽기 주체

`workspace/positions/*.md` 파일을 어디서 읽어야 하나요?

A) 데몬(Python SteeringRuntime)이 읽음 — `steer_read` 서브커맨드로 구현. 데몬이 `Journal` 클래스를 통해 파일을 읽고, 기존 channel/monitor 체계를 통해 TUI에 전달. 일관된 데이터 흐름.
B) MCP 서버(TypeScript)가 직접 읽음 — 새 MCP 툴로 구현. Node.js `fs.readFileSync`로 파일 직접 읽기. 더 단순한 구현, 데몬 의존성 없음.

[Answer]: A

---

## Question 4: Thesis 쓰기 기능 필요 여부

TUI에서 포지션 테제를 읽는 것 외에, 운영자가 TUI를 통해 thesis 파일을 수정/업데이트할 수 있는 쓰기 기능도 필요한가요?

A) 읽기만 필요 — 운영자는 thesis를 조회만 하고, 수정은 에이전트(PM agent)가 담당
B) 쓰기도 필요 — 운영자가 TUI에서 thesis를 직접 수정할 수 있어야 함 (예: `/thesis AAPL set stop=290 target=360`)

[Answer]: A

---

## Question 5: 확장 기능 — 전체 Thesis 목록 조회

현재 `workspace/positions/` 디렉토리에는 현재 보유 중인 포지션 외에 과거 매매했거나 워치리스트에 올랐던 종목들의 thesis 파일도 존재할 수 있습니다. 전체 thesis 파일 목록을 조회하는 기능도 필요한가요?

A) 필요함 — `steer_read /theses` 또는 `list_position_theses` 툴로 전체 목록을 볼 수 있게
B) 불필요 — 특정 심볼의 thesis만 조회할 수 있으면 충분

[Answer]: A

---

## Question 6: Extension Opt-In — Security Baseline

이 프로젝트에 Security Baseline 확장 규칙을 적용할까요?
(Security Baseline은 시크릿 관리, 에러 처리, 권한 분리 등 보안 규칙을 강제합니다.)

A) 예 — 모든 SECURITY 규칙을 blocking constraints로 적용 (프로덕션급 애플리케이션에 권장)
B) 아니오 — SECURITY 규칙을 건너뜁니다 (PoC, 프로토타입, 실험적 프로젝트에 적합)

[Answer]: A

---

## Question 7: Extension Opt-In — Property-Based Testing

이 프로젝트에 Property-Based Testing (PBT) 규칙을 적용할까요?

A) 예 — 모든 PBT 규칙을 blocking constraints로 적용 (비즈니스 로직, 데이터 변환, 직렬화, 상태 저장 컴포넌트가 있는 프로젝트에 권장)
B) 부분 적용 — 순수 함수와 직렬화 round-trip에만 PBT 규칙 적용 (제한된 알고리즘 복잡도를 가진 프로젝트에 적합)
C) 아니오 — PBT 규칙을 건너뜁니다 (단순 CRUD, UI 전용, 또는 중요한 비즈니스 로직이 없는 얇은 통합 레이어에 적합)

[Answer]: B
