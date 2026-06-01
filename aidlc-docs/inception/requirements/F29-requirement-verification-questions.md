# F29 — Supervisor 모드 코드베이스 오리엔테이션: 요구사항 검증 질문

> **Track**: F29 · **Phase**: INCEPTION — Requirements Analysis
> **생성일**: 2026-06-01T14:45:00Z
> **답변 방법**: 각 질문의 `[Answer]: ` 태그에 선택지를 기입하고, 필요한 경우 설명을 덧붙여주세요.

---

## 현재 상태 분석 (질문 전 참고)

**문제**: Supervisor 모드(`--supervisor`)에서 에이전트가 autostock 코드를 읽을 수 있지만(F26 권한 프로파일), 프로젝트 구조를 몰라 경로 시행착오 발생.
- 관찰된 사례: `/app/src/main.py` → File not found (존재하지 않는 경로), `/app/src/agent/prompts.py` → 성공
- Docker attach 환경에서 `AUTOSTOCK_ROOT=/app`, cwd=`/app/operator-console/cli`인데 에이전트는 이걸 모름

**현재 에이전트가 받는 정보**:
- `AGENTS.md` — `operator-console/cli/AGENTS.md`만 auto-load됨 (opencode 포크 개발 컨벤션, autostock 프로젝트 정보 없음)
- `CLAUDE.md` — 글로벌 `~/.claude/CLAUDE.md`만 로드됨. 루트 `CLAUDE.md`는 auto-load 경로 밖 (cwd 상위 디렉터리)
- `steer_read` MCP — `/status`, `/agent-trace`, `/why`, `/turns`, `/decisions`, `/log` → 운영 상태만, 코드 구조 정보 없음
- Supervisor 권한 — `read/glob/grep/lsp`가 `$AUTOSTOCK_ROOT/**` 전체 허용 (비밀 제외). **도구는 있는데 어디를 봐야 할지 모름**

**현재 루트에 없는 것**: `AGENTS.md`, `CODEBUDDY.md`, `CONTEXT.md` — 프로젝트 구조 맵 없음

---

## Q1 — 전달 메커니즘: 코드베이스 구조 정보를 어떻게 에이전트에게 전달할까?

에이전트가 supervisor 진입 시 **별도의 파일 읽기 없이** 프로젝트 구조를 알 수 있어야 한다.

**A) `AUTOSTOCK_ROOT/AGENTS.md` 신규 생성 (추천)**
- opencode가 `AGENTS.md`를 프로젝트 디렉터리에서 자동으로 찾아 system instruction으로 로드함 (`instruction.ts:121-131`)
- 단, 현재 cwd=`operator-console/cli` 기준 `findUp`하므로, `AGENTS.md`를 `operator-console/cli/`에 두면 autostock 전체가 아닌 포크 정보만 담게 됨
- → `AGENTS.md`를 `$AUTOSTOCK_ROOT/`에 두고, opencode가 루트까지 `findUp`할 수 있도록 instruction loading을 supervisor에서 확장
- 혹은 opencode config `instructions` 필드에 `$AUTOSTOCK_ROOT/AGENTS.md` 절대경로 지정

**B) Supervisor system prompt에 직접 주입**
- `opencode.json`의 `instructions` 필드나 `OPENCODE_PERMISSION`과 동일한 패턴으로 supervisor 전용 system prompt에 프로젝트 구조 요약을 삽입
- opencode config의 `instructions`는 `instruction.ts:134-148`에서 로드 → 런처가 supervisor일 때만 `instructions`에 프로젝트 맵 파일 경로를 추가하거나, 인라인 텍스트를 주입
- 장점: supervisor에만 적용, normal 영향 없음

**C) `steer_read` MCP에 `/codebase` 또는 `/map` 뷰 추가**
- `steer_read{command:/codebase}` → 데몬/런타임이 프로젝트 구조 맵을 반환
- 장점: 항상 최신 (데몬이 실시간 생성), normal에도 제공 가능
- 단점: 에이전트가 이 도구의 존재를 먼저 알아야 함 (닭이 먼저냐 달걀이 먼저냐)

**D) 기존 `CLAUDE.md` 활용 (루트 `CLAUDE.md`에 프로젝트 맵 섹션 추가)**
- 루트 `CLAUDE.md`는 이미 존재하는 방대한 AI-DLC 워크플로 문서. 여기에 간결한 "Project Map" 섹션을 추가
- opencode가 루트 `CLAUDE.md`를 supervisor에서 자동 로드하게 하면, AI-DLC 워크플로 지식 + 프로젝트 구조가 한 번에 들어옴
- 단점: normal 모드에도 로드될 위험 (normal은 권한이 없어서 못 읽겠지만, 파일 경로는 알게 됨)

**E) 복합 접근**
- 위 방식 중 여러 개를 조합 (어떤 조합인지 설명해주세요)

**[Answer]: C.**

---

## Q2 — 프로젝트 맵 내용 범위: 어느 수준까지 포함해야 하나?

**A) 최소 — 탑레벨 디렉터리 트리 + 한 줄 설명**
```
autostock/
├── src/               # Python 애플리케이션 코드
│   ├── agent/         # 에이전트 모드 (LLM PM + 결정 실행)
│   ├── trading/       # 트레이딩 엔진 + 모드
│   ├── strategy/      # 전략 구현체 (기술적/ML/LLM)
│   ├── risk/          # 리스크 관리 + 주문 게이트
│   ├── execution/     # 브로커 추상화
│   ├── data/          # 데이터 수집/변환
│   └── core/          # 공통 모델/타입
├── operator-console/  # 오퍼레이터 콘솔 (opencode 포크, TS)
├── config/            # 설정 파일 (YAML)
├── docs/              # 설계 문서
├── tests/             # 테스트
└── scripts/           # 유틸리티 스크립트
```

**B) 표준 — 패키지별 설명 + 주요 파일 포인터**
- A의 트리 + 각 패키지의 **핵심 파일**과 그 역할을 1~2문장으로 (예: `src/agent/orchestrator.py` — 에이전트 턴 시퀀싱, `src/risk/manager.py` — 모든 주문의 단일 게이트)
- "무엇을 찾을 때 어디를 보라"는 가이드 포함

**C) 상세 — 아키텍처 다이어그램 + 컴포넌트 설명 포함**
- B의 내용 + `aidlc-docs/inception/reverse-engineering/architecture.md` 기반 아키텍처 개요
- 데이터 흐름도, 레이어 의존성 규칙

**[Answer]: A. 이거만 있어도 좀 덜 헷갈릴듯**

---

## Q3 — 경로 문제: Docker vs 호스트 경로를 어떻게 처리할까?

Supervisor의 opencode fork는 Docker 컨테이너 안에서 실행될 수도 있고(`/app/...`), 호스트에서 직접 실행될 수도 있음(`/home/jihoonpark/Project/autostock/...`). 에이전트가 `/app/src/main.py`라고 추측한 건 Docker 경로지만, 실제 `main.py`는 `src/main.py`가 아니라 `main.py`(루트)에 있음.

**A) 프로젝트 맵에 경로를 AUTOSTOCK_ROOT 기준 상대경로로만 표기**
- `{AUTOSTOCK_ROOT}/src/agent/orchestrator.py` 형태로 기술
- 에이전트가 `AUTOSTOCK_ROOT` 환경변수 값을 `bash echo $AUTOSTOCK_ROOT`로 확인하게 프롬프트에 안내
- 가장 단순하지만, 에이전트가 매번 env 확인 필요

**B) 프로젝트 맵 생성 시점에 절대경로로 치환**
- 런타임에 `AUTOSTOCK_ROOT` 값을 읽어서 실제 절대경로(`/app/...` 또는 `/home/...`)로 맵을 생성
- 데몬/MCP가 동적 생성하거나, 런처가 supervisor 기동 시점에 맵 파일을 생성

**C) 둘 다 표기 — 상대경로 + 현재 세션 절대경로**
- 프로젝트 맵 앞부분에 "현재 AUTOSTOCK_ROOT=/app"이라고 명시하고, 모든 경로는 `src/agent/...` 상대형식으로 표기
- 에이전트는 `AUTOSTOCK_ROOT` + 상대경로 조합으로 읽으면 됨

**D) 경로 문제는 무시 — 에이전트가 glob/grep으로 찾게 하면 됨**
- 프로젝트 맵은 패키지 이름과 역할만 알려주고, 구체적 파일 경로는 에이전트가 `glob` 도구로 찾도록
- glob/grep이 supervisor에서 허용되어 있으므로 가능

**[Answer]: A. **

---

## Q4 — 유지보수: 프로젝트 맵을 어떻게 최신 상태로 유지할까?

**A) 수동 관리 — 구조 변경 시 개발자가 직접 업데이트**
- 간단하고 의도가 정확히 반영됨. 단, 잊어버리면 stale.

**B) 자동 생성 — 디렉터리 트리 스캔 스크립트**
- `scripts/gen-project-map.sh`가 `src/` 트리를 스캔해 맵을 생성. 패키지 설명은 `__init__.py` 독스트링에서 추출
- 구조 변경 시 자동 반영. 단, 사람 의도(왜 이렇게 구성됐는지)는 빠짐

**C) 하이브리드 — 자동 구조 + 수동 주석**
- 자동 생성된 디렉터리 트리에 사람이 패키지 설명과 주요 파일 포인터를 주석으로 추가
- 스크립트는 구조만 갱신하고 주석은 보존

**D) 데몬이 `publish_snapshot` 시 함께 생성**
- 데몬이 이미 `publish_snapshot`으로 운영 상태를 주기적으로 발행하듯, 프로젝트 구조 맵도 함께 발행
- `steer_read{command:/codebase}`로 조회 → 항상 실시간 최신

**[Answer]: D.**

---

## Q5 — F26(권한)·F28(UI 지식)과의 관계

**Q5a — F26 의존성**: 이 트랙은 F26의 supervisor 권한 프로파일이 제공하는 `read/glob/grep/lsp`를 **사용**하는가, 아니면 **수정**이 필요한가?

- **A) 사용만 함 (권한 변경 없음)** — F26이 허용한 read/glob/grep/lsp 위에서 프로젝트 맵 정보만 추가 제공
- **B) F26 수정 필요** — 예: opencode config `instructions` 필드 조정, instruction 로딩 범위 확장 등 작은 변경
- **C) F26 큰 수정 필요** — 권한 프로파일 자체를 변경해야 함

**[Answer Q5a]: A **

**Q5b — F28 관계**: F28은 normal-mode 에이전트에게 TUI 요소의 의미를 설명하는 지식을 제공하는 트랙. F29(supervisor 코드 구조 지식)와 F28(normal UI 지식)은 지식 제공이라는 점에서 유사하다. 하나의 공통 메커니즘으로 통합할 필요가 있을까?

- **A) 별도 트랙 유지 (현행)** — 지식 도메인이 다르고(supervisor=코드구조, normal=UI), 전달 대상이 다르므로 분리
- **B) 공통 지식 제공 메커니즘 설계** — `steering/knowledge/` 디렉터리에 지식 파일들을 두고, 두 모드가 각자 필요한 파일만 읽는 구조
- **C) 하나의 트랙으로 합병** — F28+F29를 합쳐 "에이전트 지식 베이스"로 통합 개발

**[Answer Q5b]: A **

---

## Q6 — supervisor system prompt 자체에 대한 확장

현재 supervisor와 normal은 같은 system prompt(오픈코드 기본 프롬프트 + AGENTS.md)를 공유하는데, supervisor에는 코드 탐색 도구(read/glob/grep/lsp)가 추가로 있다. **supervisor에 특화된 system prompt 지침**(예: "코드를 읽을 때는 먼저 프로젝트 맵을 참조하라", "AUTOSTOCK_ROOT 환경변수를 확인하라")이 필요할까?

- **A) 필요 없음** — 프로젝트 맵만 제공되면 기본 프롬프트로 충분
- **B) 최소 지침 추가** — 프로젝트 맵 위치/사용법을 프롬프트 앞부분에 1~2줄 추가
- **C) supervisor 역할 설명 추가** — "너는 autostock의 supervisor 모드다. 코드를 읽고 daemon의 동작을 설명하는 것이 주 역할이다. 수정은 금지된다" 같은 역할 프롬프트

**[Answer]: B. 코드베이드/autostock 구현에 대해서 물을때 참조할 수 있도록. **

---

## Q7 — 적용 대상: supervisor와 normal 모두에게 도움이 될까?

Q1의 메커니즘 선택에 따라, 프로젝트 구조 정보가 normal 모드 에이전트에게도 노출될 수 있다. 이것이 바람직한가?

- **A) 바람직함** — normal도 운영 중 "데몬이 뭘 하는지" 기본적인 구조 이해는 도움이 됨
- **B) supervisor only** — normal은 코드 구조를 알 필요 없음. 운영 상태만으로 충분
- **C) normal에는 축약 버전 제공** — normal에는 최소한의 구조 정보만, supervisor에는 전체 맵

**[Answer]: B. normal은 F28에서 만드는 UI 관련 정보만 알면 됨**

---

## Q8 — Docker attach 경로 특수 처리

Docker attach 모드(`docker compose -f docker-compose.verify.yml run --rm verify attach`)에서는 opencode가 컨테이너 안에서 실행된다. 호스트와 다른 점:
- `AUTOSTOCK_ROOT=/app` (bind-mount)
- `~/.claude`는 호스트에서 read-only 마운트 (LLM 인증)
- `STEERING_DIR`, `workspace/` 등은 컨테이너 내 경로

이 환경에서 프로젝트 맵이 제대로 동작하려면 추가 고려사항이 있을까?

- **A) 특별 처리 불필요** — `AUTOSTOCK_ROOT` 기반 상대경로로만 표기하면 호스트/컨테이너 양쪽에서 동작
- **B) Docker 환경 감지 필요** — Docker 안인지 감지해서 경로를 조정하는 로직 필요
- **C) Docker 전용 설정 파일** — `AGENTS.md`를 Docker 컨테이너 내에서 별도 생성/마운트

**[Answer]: A **

---

> **모든 질문에 답변을 `[Answer]: ` 태그에 기입해주세요.**
> 답변이 모이면 모호한 점을 분석하고 requirements.md를 생성합니다.
