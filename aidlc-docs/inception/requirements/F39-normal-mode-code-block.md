# F39 — Normal 모드 코드 질문 차단: 요구사항

> Track F39 · feature (behavior hardening) · Brownfield · Requirements depth: **Standard**
> 질문/답변: `F39-normal-mode-code-block-questions.md` (2026-06-03 answered).

## 1. 문제 정의
운영자 콘솔(opencode 포크) 에이전트가 **supervisor 모드가 아닌 normal 모드**에서, 권한상 소스 파일을
읽지 못함에도 (1) 소스 읽기를 *시도*하고 (2) `/codebase` 트리 + 추측으로 코드 내부를 *설명*한다.
사용자 요구: "SUPERVISOR MODE가 아니면 아예 코드 관련해서 답을 못하게끔 해야 해."

### 1.1 현재 동작 (코드 확인 결과)
- **권한 벽은 이미 동작**: `opencode.json` `"*": "deny"` + F26 normal 프로필 →
  `external_directory`/`read`는 `$STEERING_DIR`만 허용, `glob`/`grep`/`lsp`는 normal에서 tool 제거.
  → 소스 파일 직접 read/검색은 차단됨(transcript의 `Read orchestrator.py` 실패가 그 증거).
- **그러나** 두 가지가 코드 어시스턴트형 행동을 가능케 함:
  - (a) **운영자 전용 페르소나/시스템 프롬프트 부재** → 에이전트가 opencode 기본 "코딩 어시스턴트"
    프롬프트로 동작, 소스 읽기·내부 설명을 당연하게 시도.
  - (b) `autostock_steer_read`(= `/codebase` 프로젝트 트리, F29)가 `opencode.json`에서 **두 프로필 모두
    `allow`** → normal 모드에서도 코드 구조를 받아 추론 가능.

## 2. 확정 결정 (질문 답변)
| # | 결정 | 답변 |
|---|------|------|
| Q1 | **거부 범위 = 소스/구현 내부 질문만**. 운영/런타임 질문은 `steer_read`(monitor/snapshot) 데이터로 계속 응답하되 **소스 추측 금지**; 데이터로 못 답하면 모른다고 함. | A |
| Q2 | **강제 = 프롬프트 가드 + 구조적 차단** (defense-in-depth). | A |
| Q3 | **`/codebase` 트리 = supervisor 전용**으로 제한(normal에서 차단). | A |
| Q4 | **거부 UX = 정중히 거부만**, supervisor 모드는 **언급하지 않음**(개발자 전용 숨은 기능 유지). | B |
| Q5 | **Security Baseline = Enabled**, **PBT = Disabled**. | — |

> **정합성 메모**: Q4=B(거부 메시지에 supervisor 미언급)가 Q2/Q3 옵션 설명의 "supervisor 안내" 문구를
> 무효화한다. 모든 normal-mode 거부 메시지(코드 질문 거부 + `/codebase` 차단 응답)는 supervisor를
> 언급하지 않는 **일반적 표현**만 사용한다.

## 3. 기능 요구사항 (FR)
- **FR-1 (페르소나 가드)**: normal 모드에서 운영자 에이전트는 **운영자 어시스턴트 역할**로 동작한다.
  소스 코드/구현 내부(파일 내용, 함수 동작, 클래스 구조, "이 코드 어떻게 동작?")에 대한 질문은
  **답하지 않고 정중히 거부**한다. 추측·재구성으로 코드 내부를 설명하지 않는다.
- **FR-2 (운영 질문 유지)**: 운영/런타임 상태 질문(예: "왜 turn이 안 돌아?", "지금 포지션/계좌?",
  "오늘 체결?")은 **`steer_read`(monitor/snapshot) + 허용된 MCP read 도구**로 계속 응답한다.
  단 답이 운영 데이터로 도출되지 않으면 **모른다고 말하고**, 소스를 추측해 메우지 않는다.
- **FR-3 (코드 읽기 시도 억제)**: normal 모드에서 에이전트는 소스 파일 읽기/검색을 **시도하지 않는다**
  (권한으로 막히는 호출을 반복하지 않음). 프롬프트로 명시.
- **FR-4 (`/codebase` supervisor 전용)**: `autostock_steer_read`의 `/codebase`(프로젝트 트리) verb는
  **supervisor 모드에서만** 동작한다. normal 모드에서 호출되면 트리를 반환하지 않고, supervisor를
  언급하지 않는 **일반 거부 메시지**를 반환한다. (구조적 차단 — FR-1 프롬프트 가드의 backstop)
- **FR-5 (supervisor 동작 보존)**: supervisor 모드의 코드 분석 능력(전체 read + `/codebase`)은 **그대로
  유지**된다. 이 트랙은 normal 모드만 강화한다.
- **FR-6 (운영자 read MCP 보존)**: 계좌/포지션/시세 등 `autostock_get_*` 및 `steer_read`의 비코드
  verb(예: `/ui-legend`, monitor/snapshot 뷰)는 normal 모드에서 **계속 동작**한다.

## 4. 비기능 요구사항 (NFR)
- **NFR-1 (defense-in-depth, 정확한 범위)**: 강제는 세 층이지만 각 층의 **커버리지가 다르다**(critic HIGH#2로 정정):
  - **L0 (권한 벽, F26)**: 소스 파일 `read`/`glob`/`grep`을 **구조적으로 차단**. 우회 불가의 하드 보장.
  - **L2 (`/codebase` 게이팅, FR-4)**: 프로젝트 트리 노출을 supervisor 전용으로 **구조적 차단**. 단 이는
    `/codebase` verb **하나**만 막는다 — 코드 구조 노출 전반을 막는 게 아니다.
  - **L1 (프롬프트/페르소나, FR-1/3)**: 위 두 하드 게이트가 **막지 못하는** 부분 = 도구 없이 모델이 자체 지식/
    문맥으로 코드 동작을 추측·재구성하는 "프리폼 코드 추론"을 억제한다. **이 부분은 L1만이 담당**(소프트).
  - 즉 "소스 읽기"·"트리 조회"는 하드 차단되지만, **프리폼 코드 추측**은 L1(프롬프트)에 의존한다.
  - 또한 운영자 페르소나는 컨텍스트에 함께 로드되는 opencode 포크 **개발자용 `AGENTS.md` 2개**
    (`cli/AGENTS.md`, `packages/opencode/AGENTS.md`)와 포크 기본 코딩-어시스턴트 프롬프트를 **무시하도록 명시**해야
    한다(operator.md). 이들은 구조적으로 제거 불가(프로젝트 config 통째 비활성화 = `opencode.json` 권한/MCP까지
    날아감 → 채택 불가)이므로, L1은 salience(후미 로드) + 명시적 무시 지시에 의존한다 → **AR-1**.
- **NFR-2 (개발자 전용 노출 최소화)**: normal 모드 사용자에게 supervisor 모드의 존재/사용법을 노출하지
  않는다(거부 메시지·`/codebase` 차단 메시지 모두). 단 코드/문서/CLI stderr의 기존 `--supervisor` 표기는 그대로.
- **NFR-3 (회귀 없음)**: 기존 normal/supervisor 권한 프로필, `verify-lockdown`, registry 테스트, F28
  `/ui-legend`, F29 supervisor `/codebase` 동작 모두 회귀 없이 통과.

## 5. 범위 밖 (Out of scope)
- supervisor 모드 자체의 변경(권한 프로필, 진입 방식). F26/F29 그대로.
- 트레이딩/주문 경로, 데몬 로직.
- normal 모드에서 *운영 데이터*로 답할 수 있는 범위 확장(별도 트랙).

## 6. Extension 적용
- **Security Baseline (Enabled)**: 적용 — SECURITY-03(거부/트리 메시지에 비밀·경로 노출 금지),
  SECURITY-15(`/codebase` 게이팅 fail-closed: supervisor 확인 안 되면 거부). 노출 표면을 *좁히는* 변경이라
  새 비밀 노출 없음. 그 외(웹앱/DB/IaC/auth)는 N/A.
- **Property-Based Testing (Disabled)**: 프롬프트/설정 + 단순 게이팅 분기 → 알고리즘 로직 없음.

## 7. 영향 파일 (예상 — 설계에서 확정)
- 프롬프트 가드(FR-1/2/3): 운영자 에이전트 system prompt/instructions 주입 지점
  (현재 autostock 전용 프롬프트가 없으므로 **신규**; 후보 = 포크의 agent instructions / `AGENTS.md` /
  launcher가 주입하는 프롬프트 — 설계에서 가장 깔끔한 carrier 선정).
- `/codebase` 게이팅(FR-4): `operator-console/src/steer-handler.ts`(`verb === "codebase"` 분기),
  `parser.ts`, `mcp-server.ts` 설명 — supervisor 여부는 `AUTOSTOCK_SUPERVISOR` env로 판정(F26 패턴).
- 테스트: steer-handler/parser 게이팅 + (가능 시) verify-lockdown/registry 회귀.

## 8. 리스크
- **Low–Medium**: 운영자 콘솔 전용, 트레이딩/데몬 경로 무관, worktree 격리 → 롤백 용이.
  주의점 = `/codebase` 게이팅이 supervisor 정상 동작을 깨지 않을 것(NFR-3), 프롬프트 가드가 운영 질문까지
  과하게 거부하지 않을 것(FR-2 균형).

## 9. Accepted Residuals (critic 2026-06-03)
- **AR-1 (프리폼 코드 추론은 L1-only)**: 소스 읽기(L0)·`/codebase` 트리(L2)는 하드 차단되지만, 도구 없이
  모델이 코드 동작을 추측·재구성하는 프리폼 추론은 프롬프트(L1)로만 억제된다. 컨텍스트에 함께 로드되는 포크
  개발자용 `AGENTS.md` 2개 + 기본 코딩-어시스턴트 프롬프트를 구조적으로 제거할 수 없어(프로젝트 config 통째
  비활성화는 F26 권한/MCP까지 파괴 → 불가), operator.md의 명시적 무시 지시 + 후미-로드 salience에 의존.
  사용자 선택(Q2=A: 프롬프트+`/codebase` 구조 차단)과 정합. 잔여 위험 수용.
- **AR-2 (supervisor 진입의 개발자 신뢰 경계)**: MCP 자식은 `{...process.env, ...mcp.environment}`로 콘솔 env를
  상속하므로, 런처를 거치지 않고 `AUTOSTOCK_SUPERVISOR=on bun dev`를 직접 실행하면 `/codebase`가 열린다(단
  권한 프로필/페르소나는 런처만 주입하므로 미적용). 이는 셸 접근을 가진 **개발자의 의도적 행위** = `--supervisor`와
  동일 신뢰 수준이며 모델/데몬이 도달할 수 없는 경로(F26 개발자 전용 가드). 런처 정상 경로(normal)는
  key 삭제 + `{env:}`→"" overlay로 **견고히 fail-closed**(verify-lockdown PASS). 수용.
