# F53 요구사항 문서 — MCP Position Thesis 노출

## Intent Analysis Summary

| 항목 | 내용 |
|------|------|
| **요청 유형** | Enhancement (기존 기능 개선) |
| **범위** | Multiple Components — MCP 서버(TypeScript) + 데몬 SteeringRuntime(Python) |
| **복잡도** | Moderate — 기존 channel/steer_read 패턴 재사용, 신규 파일 읽기 경로 추가 |
| **사용자 요청** | TUI에서 `get_all_positions`로 브로커 포지션(수량, 평단가, 손익)만 확인 가능. 에이전트가 `workspace/positions/*.md`에 기록하는 포지션 테제(thesis, stop/target, Call-vs-Outcome)를 MCP를 통해 조회할 수 있도록 개선 |

---

## 기능 요구사항 (Functional Requirements)

### FR-1: Thesis 파일 읽기 — `steer_read /thesis <SYMBOL>`
- **설명**: `steer_read`에 `/thesis <SYMBOL>` 서브커맨드를 추가하여, 데몬이 `workspace/positions/<SYMBOL>.md` 파일을 읽고 원본 markdown 내용을 그대로 반환
- **입력**: 유효한 stock symbol (예: `AAPL`, `MSFT`)
- **출력**: 해당 symbol의 thesis markdown 파일 전체 내용 (raw text). 파일이 존재하지 않으면 적절한 메시지 반환
- **구현 위치**: Python 데몬 `SteeringRuntime` → `steer_read` 핸들러 → `Journal.read_position(symbol)`
- **승인 결정**: Q1=A, Q2=A, Q3=A

### FR-2: Thesis 파일 목록 조회 — `steer_read /theses`
- **설명**: `steer_read`에 `/theses` 서브커맨드를 추가하여, `workspace/positions/` 디렉토리에 존재하는 모든 thesis 파일 목록을 반환
- **입력**: 없음
- **출력**: thesis 파일이 존재하는 symbol 목록 (예: `AAPL, GOOGL, MSFT, RTX`)
- **구현 위치**: Python 데몬 `SteeringRuntime` → `steer_read` 핸들러 → `Journal.list_positions()`
- **승인 결정**: Q5=A

### FR-3: 읽기 전용 (Read-Only)
- **설명**: 운영자는 thesis를 조회만 가능. 수정은 PM 에이전트만 담당
- **승인 결정**: Q4=A

---

## 비기능 요구사항 (Non-Functional Requirements)

### NFR-1: 기존 아키텍처 패턴 재사용
- `steer_read`의 기존 서브커맨드(`/status`, `/turns`, `/log` 등)와 동일한 패턴으로 구현
- 데몬이 파일을 읽고, 기존 channel/monitor 응답 체계를 통해 결과 반환
- 신규 의존성 없음 (stdlib `pathlib` + 기존 `Journal` 클래스 사용)

### NFR-2: 장애 허용 (Fail-Closed)
- Thesis 파일이 존재하지 않는 경우: `"No thesis file found for <SYMBOL>"` 메시지 반환 (에러 throw 금지)
- `workspace/positions/` 디렉토리가 없는 경우: `/theses` 요청 시 빈 목록 반환
- 파일 읽기 권한 문제: 명확한 에러 메시지 반환

### NFR-3: 보안 — SECURITY-03 (No Secrets in Logs)
- Thesis 파일 내용을 로그에 출력하지 않음
- 파일 경로만 로깅하고, 내용은 반환값으로만 전달

### NFR-4: 보안 — SECURITY-15 (Fail-Closed Error Handling)
- 모든 파일 I/O 예외를 명시적으로 처리
- 파일 읽기 실패 시 데몬이 중단되지 않아야 함

---

## 아키텍처 결정

### AD-1: 구현 위치 — 데몬(Python)
- **결정**: MCP 서버(TypeScript)가 아닌 데몬(Python SteeringRuntime)에서 파일 읽기 수행
- **근거**: 
  - `Journal` 클래스(`src/agent/journal.py`)가 이미 `read_position()`, `list_positions()` 메서드 제공
  - 기존 `steer_read` 서브커맨드 패턴과 일관성 유지
  - 데몬이 `workspace/` 디렉토리 구조를 이미 인지하고 있음

### AD-2: 데이터 형식 — Raw Markdown
- **결정**: Thesis 파일 내용을 파싱하지 않고 원본 markdown 그대로 반환
- **근거**: 
  - 마크다운 파싱/구조화는 불필요한 복잡도 추가
  - TUI의 opencode agent(LLM)가 raw markdown을 받아 알아서 요약/전문 표시 가능
  - Thesis 파일 형식이 에이전트 프롬프트에 따라 변할 수 있어 파싱이 fragile해짐

### AD-3: steer_read 서브커맨드로 통합
- **결정**: 새 독립 MCP 툴이 아닌 `steer_read`의 새 서브커맨드로 구현
- **근거**:
  - MCP 서버(TypeScript)는 `steer_read`를 이미 file-drop → daemon 응답 구조로 처리 중
  - `/thesis`, `/theses`는 daemon의 읽기 전용 상태 조회라는 점에서 `/status`, `/turns`와 동일한 성격
  - MCP 서버 변경 최소화 (기존 `steer_read` 파이프라인 재사용)

---

## 영향 범위 (Impact Surface)

| 파일 | 변경 내용 |
|------|----------|
| `src/agent/steering/runtime.py` | `SteeringRuntime._handle_steer_read()`에 `/thesis`, `/theses` 서브커맨드 추가 |
| `src/agent/steering/channel.py` | `monitor.json` 또는 `snapshot.json`에 thesis 응답 포함 (또는 별도 응답 채널) |
| `src/agent/journal.py` | 변경 없음 — 기존 `read_position()`, `list_positions()` 재사용 |
| `operator-console/src/mcp-server.ts` | `steer_read` 툴 설명에 `/thesis`, `/theses` 문서화 (선택적) |
| `operator-console/src/steer-handler.ts` | 변경 없음 — 기존 `handleSteerRead`가 새 서브커맨드를 투명하게 전달 |

---

## 구현 전략 (Implementation Strategy)

### 변경 범위가 작은 이유
`steer_read`는 현재 **pass-through** 구조: MCP 서버가 서브커맨드 문자열을 file-drop으로 전달하고, 데몬이 파싱하여 응답을 생성한 후, 그 응답을 다시 file-drop 채널을 통해 반환.

따라서:
1. **데몬 측**: `steer_read` 핸들러에 `/thesis <SYMBOL>`, `/theses` 두 가지 케이스만 추가
2. **MCP 서버 측**: 변경 불필요 (기존 `steer_read` 툴이 새 서브커맨드를 그대로 전달)

실제 구현 변경은 **데몬 Python 코드 1개 파일**에 집중될 가능성이 높음.

---

## Extension Configuration

| Extension | Enabled | Mode | 적용 규칙 |
|-----------|---------|------|----------|
| Security Baseline | Yes | Full | SECURITY-03, SECURITY-15 (others N/A — local daemon, no cloud infra) |
| Property-Based Testing | Yes | Partial | PBT-02, PBT-03, PBT-07, PBT-08, PBT-09 (순수 함수 + 직렬화 round-trip only) |
