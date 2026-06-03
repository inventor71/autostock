# F26 — Supervisor Mode 요구사항 확인 질문

> 각 질문의 `[Answer]:` 태그 뒤에 답을 적어주세요. 보기(A/B/C…) 중 고르거나 `X) Other`로 자유 기술 가능합니다.
> 답변이 모두 채워지면 요구사항 문서(`requirements.md`)를 작성하고 다음 단계로 넘어갑니다.

## 배경 (코드 확인 결과)

지금 콘솔 에이전트가 "research turn 요약해줘"에서 막힌 이유는 권한 모델 때문입니다:

- 런처(`operator-console/launcher/config.ts:110`)가 `AUTOSTOCK_LOCKDOWN=on`으로 콘솔을 띄우고, 콘솔의 cwd는 `operator-console/cli` 서브모듈입니다. 그래서 에이전트의 "프로젝트 디렉터리"는 cli 트리뿐입니다.
- 상위 autostock(파이썬 본체) 코드 읽기는 **`external_directory` 권한**으로 막혀 있습니다(`opencode.json`이 `"*": "deny"`라 allowlist에 없는 `external_directory`는 거부). → 캡처에서 "상위 루트가 도구 권한상 막혀있다"가 바로 이 벽입니다.
- `registry.ts` lockdown은 edit/write/bash/task/fetch/patch 빌트인을 아예 **컴파일에서 제거**합니다. read/glob/grep/lsp + MCP만 남습니다. → "읽기 전용/수정 금지"는 이미 구조적으로 보장됩니다(supervisor 모드도 쓰기 도구를 추가하지 않으며 추가해서도 안 됨).
- 참고: 파서 환경에 `AUTOSTOCK_ROOT`(상위 레포 절대경로)가 이미 콘솔 env로 전달됩니다(`config.ts:107`). 즉 supervisor 모드의 읽기 범위를 `$AUTOSTOCK_ROOT`로 스코프하기 쉽습니다.

---

## Question 1: supervisor 모드 진입 방식 (UX)
운영자가 어떻게 supervisor 모드로 들어가나요?

A) **opencode 에이전트/페르소나로 추가** — TUI에서 에이전트 전환(Tab) 또는 `@supervisor` 멘션으로 그 턴/세션만 supervisor로. (기본 에이전트는 그대로 잠김) — *권장: opencode 네이티브 모델에 가장 자연스럽고, 모드별 권한/프롬프트 분리가 깔끔함*
B) **세션 전역 토글** — 콘솔 실행 시 플래그(예: `autostock --supervisor`)나 TUI 커맨드(`/supervisor on|off`)로 세션 전체를 전환
C) **데몬/질문 유형 기반 자동 전환** — 질문이 "자기 코드 동작"에 관한 것이면 자동으로 코드 읽기 허용
X) Other (please describe after [Answer]: tag below)

[Answer]: B. autostock --supervisor가 유일한 진입.

---

## Question 2: 두 모드의 동시 사용 형태
normal과 supervisor를 어떻게 쓰고 싶나요?

A) **한 세션 안에서 전환** — 같은 대화에서 평소엔 normal, 필요할 때 supervisor로 바꿨다가 돌아옴 (대화 맥락 유지)
B) **별도 세션/별도 에이전트** — supervisor는 분석 전용 별도 세션(또는 별도 에이전트)이고 일반 스티어링과 섞지 않음 — *권장: 코드열람 컨텍스트와 매매 컨텍스트를 격리해 사고 위험↓*
C) 상관없음 — 설계자가 적절히 결정
X) Other

[Answer]: supervisor 모드일때 그냥 권한이 더 많은것. supervisor 모드로 키면 권한 많은 세션이 되는거고, --supervisor 안붇히면 normal 권한만 있음 (Q-1의 방식)

---

## Question 3: supervisor 모드에서 매매/스티어링 MCP 도구 허용 여부
supervisor(코드 읽기 가능) 상태일 때 `autostock_steer` / `place_stock_order` / `close_position` 같은 **쓰기성 MCP 도구**도 같이 쓸 수 있어야 하나요?

A) **아니오 — 순수 읽기 전용 분석 모드** — supervisor에서는 코드 read + 읽기 전용 MCP(get_*/steer_read)만. 매매·스티어링 쓰기 도구는 모두 비활성. — *권장: "전체 코드를 보면서 동시에 매매까지" 결합 위험 제거; 분석↔실행 분리*
B) **예 — 동일하게 유지** — 코드도 보고 매매 스티어링도 normal과 동일하게(human-gated `ask`) 가능
C) 일부만 — (어떤 도구를 남길지 Other에 기술)
X) Other

[Answer]: B

---

## Question 4: supervisor 읽기 범위 & 제외 대상
"전체 코드 읽기"의 정확한 범위와 제외 대상은?

A) **`$AUTOSTOCK_ROOT` 전체(서브모듈 포함) 읽기, 단 민감정보 제외** — `.env*`, `secrets`, `*.key/*.pem`, `logs/`(자격증명 누출), `.git/`는 읽기 차단. 소스/문서/설정은 허용. — *권장*
B) 소스 코드만 — `src/`, `operator-console/` 등 코드 디렉터리만 허용하고 나머지는 차단
C) 루트 전체를 제한 없이 — 별도 제외 없음(어차피 단일 운영자 로컬)
X) Other (제외/포함 목록 기술)

[Answer]: A

---

## Question 5: normal 모드의 "코드 접근 차단" 강도
지금 normal 모드는 cli 서브모듈 안의 소스는 read/glob/grep으로 읽을 수 있습니다(상위 파이썬만 막힘). 요청하신 "normal은 오직 MCP + 권한있는 파일만"을 어디까지 적용할까요?

A) **strict 화이트리스트** — normal에서는 코드 파일 읽기를 끄고, **명시 허용 경로만** read 가능: `steering/`(monitor.json·snapshot.json 등 운영 상태 파일), 운영자용 README/문서 정도. 나머지 소스(cli·python) 읽기 차단. — *권장: 요청 문구 그대로. 단 어떤 경로를 "권한있는 파일"로 둘지 답에 보태주세요*
B) **현행 유지(상위만 차단)** — normal에서 cli 소스 read는 계속 허용, 상위 autostock만 막힘(=지금 상태). supervisor만 추가
C) MCP 전용 — normal에서는 파일 read 도구 자체를 끄고 MCP 도구만 (steer_read가 운영 상태를 전달)
X) Other

[Answer]: A. normal mode에서는 mcp와 그냥 인터넷 검색 같은 일반 툴만 잘 쓸 수 있어도 됨

---

## Question 6: 답변/표시
운영자가 모드를 헷갈리지 않도록 TUI가 현재 모드를 표시해야 하나요? (예: 사이드바/헤더에 `MODE: supervisor (read-only)` 배지)

A) 예 — 현재 모드를 항상 시각적으로 표시(+supervisor일 때 "read-only 분석" 경고색)
B) 아니오 — 표시는 불필요
X) Other

[Answer]: A. supervisor mode일때만 "MODE: SUPERVISOR" 표기

---

## Question 7 (보안 확장 opt-in)
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications) — *이 기능은 매매 에이전트의 읽기 표면을 자기 소스/비밀까지 넓히므로 권장*
B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)
X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 8: "개발자만 사용 가능" 강제 — 방어책 강도
supervisor 모드는 코드 전체 읽기를 여는 권한 상승이라 **개발자(=당신)만** 진입할 수 있어야 합니다. 위협은 "다른 사람"이 아니라 ① LLM 자가 권한 상승(인젝션 포함) ② 자율 데몬 경로입니다. 어느 층까지 둘까요? (여러 층 누적 가능 — 권장은 ①+②+④)

A) **①+② (구조적, 권장)** — supervisor를 `primary` 에이전트로 정의(모델은 전환 도구 없음; `task`는 lockdown이 컴파일 제거) **+** supervisor 에이전트는 별도 실행 경로에서만 등록(`autostock supervise` 서브커맨드 또는 `AUTOSTOCK_SUPERVISOR=1`, 셸 접근 필요). 평소 데몬/자율 콘솔엔 supervisor가 아예 존재하지 않음.
B) **①+②+③ (+비밀 게이트)** — 위에 더해 진입에 개발자 비밀(`AUTOSTOCK_SUPERVISOR_TOKEN`)을 요구하고 그 값을 `scrub_agent_env`로 에이전트 env에서 제거(프롬프트 인젝션 방어).
C) **①만** — supervisor를 사람만 고르는 primary 에이전트로 두는 것으로 충분(별도 런치 게이트 없이, 평소 콘솔에서도 사람이 Tab으로 전환 가능)
D) **전부(①+②+③+④)** — 위 모두 + 진입 감사 로그 + TUI 모드 배지
X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 9 (속성 기반 테스트 확장 opt-in)
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints
B) Partial — enforce PBT rules only for pure functions and serialization round-trips
C) No — skip all PBT rules (suitable for simple config/permission layers with little algorithmic logic) — *이 트랙은 권한/모드 설정 위주라 C가 무난*
X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question 10 (후속): "일반 툴"(웹) 범위 & exfil 방어 — Q5/Q7 충돌 해소
Q5에서 normal 모드에 "인터넷 검색 같은 일반 툴"을 원하셨습니다. 이는 lockdown이 컴파일 제거한 `webfetch`/`websearch`를 되살리는 변경이며, Security baseline(Q7=A)과 맞물려 데이터 유출(exfiltration) 표면을 만듭니다. 어디까지 켤까요?

A) **websearch만 (권장)** — 검색 질의(요약 결과만 반환)는 허용, 임의 URL `webfetch`는 **비활성**. 유출 통로 최소. normal·supervisor 동일.
B) **websearch + webfetch 모두** — 임의 URL fetch까지 허용(리서치 자유). 유출 위험 수용. (Security 규칙상 supervisor에서는 위험 큼)
C) **websearch는 양쪽, webfetch는 도메인 allowlist** — fetch는 명시 허용 도메인만(예: 금융/뉴스 사이트). 목록은 Other에 기술.
D) **둘 다 끔** — normal은 순수 MCP 전용(웹 없음). "일반 툴"은 보류.
X) Other

[Answer]: B

### 부속 확인 (Q10에 곁들여 답해주세요)
- (a) 웹 도구는 **normal·supervisor 양쪽** 모두 동일하게 적용하면 되나요? (supervisor는 normal의 상위집합이므로 기본은 "양쪽 동일") → [Answer]: 양쪽 동일
- (b) normal 모드의 "권한있는 파일" 읽기 allowlist는 `$STEERING_DIR/**`(monitor.json·snapshot.json·events) 읽기 전용으로 두면 충분한가요? (그 외 소스 파일 읽기 전면 차단) → [Answer]: 응. 관련해서 혹시 모를 분산된 파일 구조를 이번 트랙에서 확인하고, 만약 분산되어있다 하면 한곳으로 모으는 리펙토링 필요함. 이를 꼭 인지하고 처리 혹은 확답을 하도록 함
