# F39 — 실행 계획 (Workflow Planning)

> Track F39 · Brownfield · 요구사항: `inception/requirements/F39-normal-mode-code-block.md` (APPROVED).
> 리스크: **Low–Medium** (운영자 콘솔 전용, 트레이딩/데몬 경로 무관, worktree 격리 → 롤백 용이).

## 1. 단계 결정 (Stage Determination)
| 단계 | 실행? | 사유 |
|------|-------|------|
| Workspace Detection | ✅ done | brownfield, RE 아티팩트 존재 |
| Reverse Engineering | ⛔ skip | 아티팩트 존재 |
| Requirements Analysis | ✅ done | Standard depth, APPROVED |
| User Stories | ⛔ skip | 단일 운영자 페르소나, 동작/설정 변경 — 새 사용자 여정 없음 (F26/F29 일관) |
| Workflow Planning | ✅ (이 문서) | 항상 |
| Application Design | ⛔ skip | 새 컴포넌트 없음 — 기존 프롬프트 주입 경로 + 기존 `/codebase` verb 게이팅 |
| Units Generation | ⛔ skip | 단일 응집 변경 |
| **Construction — unit `normal-mode-code-block`** | | |
| · Functional Design | 🟡 **light (이 문서 §3에 포함)** | 거부 경계 스펙 + carrier 결정만; 별도 산출물 불필요 (F26/F29 선례) |
| · NFR Requirements | ⛔ skip | **0 new deps** (프롬프트 텍스트 + 기존 env 주입 패턴 재사용) |
| · NFR Design | ⛔ skip | NFR Req skip |
| · Infrastructure Design | ⛔ skip | 로컬 CLI, 인프라 변경 없음 |
| · Code Generation | ✅ | 프롬프트 가드 + `/codebase` 게이팅 + 테스트 |
| Build & Test | ✅ | tsgo typecheck + steer-handler/parser 게이팅 테스트 + verify-lockdown/registry 회귀 + tui-trading 빌드 |

## 2. 근본 원인 (코드 확인 완료)
1. **운영자 전용 프롬프트 부재** — opencode는 시스템 프롬프트를 `[...env, ...instructions, ...skills]`로
   조립(`cli/packages/opencode/src/session/prompt.ts:1441`). 콘솔 cwd = `operator-console/cli`이므로 현재
   instructions로 **`cli/AGENTS.md`(= opencode 포크 개발 가이드: "regenerate SDK", "default branch dev",
   commit 스타일)**가 로드됨 → 에이전트가 "나는 opencode 코드를 다루는 코딩 어시스턴트"로 행동.
2. **`/codebase` 트리가 두 프로필 모두 `allow`** — `opencode.json` `autostock_steer_read: "allow"`,
   `steer-handler.ts:144 verb === "codebase"`가 supervisor 여부와 무관하게 트리 반환.

## 3. 설계 (light Functional Design)

### 3.1 거부 경계 스펙 (FR-1/2/3)
운영자 어시스턴트 페르소나가 normal 모드에서 따르는 규칙:
- **거부 대상(소스/구현 내부)**: 파일 내용, 함수/클래스 동작, "이 코드 어떻게 동작?", 내부 알고리즘/구조,
  특정 모듈 구현 설명. → 정중히 한 문장 거부, **추측·재구성 금지**.
- **응답 대상(운영/런타임)**: 계좌·포지션·시세·체결·주문 상태, "왜 turn이 안 돌아?"류 → `steer_read`
  (monitor/snapshot) + `autostock_get_*`로 답. 데이터로 도출 불가 시 **"확인 불가"**라고 말하고 끝(추측 금지).
- **시도 억제**: 소스 파일을 읽거나 검색하려 하지 않는다(권한으로 막히는 호출 반복 금지).
- **거부 메시지**: supervisor 모드를 **언급하지 않음**(NFR-2, Q4=B). 예: "이 콘솔은 운영(트레이딩 상태)
  지원용이라 소스 코드/구현 내부 질문에는 답할 수 없어요. 계좌·포지션·시세·체결 같은 운영 질문을 도와드릴게요."

### 3.2 Carrier 결정
- **프롬프트 가드 (L1)**: 운영자 instruction 파일을 신규 작성하고, **launcher가 프로필별로 주입**.
  - 신규: `operator-console/cli/.autostock/operator.md` — 운영자 페르소나(공통, 항상). 트레이딩 운영
    어시스턴트 역할 + 사용 가능한 MCP read 도구 안내.
  - 신규: `operator-console/cli/.autostock/normal-guard.md` — §3.1 거부 규칙(normal 전용).
  - launcher(`config.ts` `consoleEnv`)가 기존 `OPENCODE_PERMISSION` 주입 옆에 **`OPENCODE_CONFIG_CONTENT`**
    (config.ts:666, "local" source로 merge)로 `{ "instructions": [...] }` 주입:
    - normal → `[".autostock/operator.md", ".autostock/normal-guard.md"]`
    - supervisor → `[".autostock/operator.md"]` (코드 분석 능력 보존; 추가 supervisor 안내 불필요)
  - **AGENTS.md 간섭 처리**: opencode가 cwd의 `cli/AGENTS.md`를 instructions로 자동 로드하는지 코드 구현
    단계에서 확인하고, 자동 로드된다면 운영자 instruction이 우선/대체되도록 정리(또는 무해 확인). critic 항목.
- **구조적 게이팅 (L2, FR-4)**: `steer-handler.ts`의 `verb === "codebase"` 분기에서 `AUTOSTOCK_SUPERVISOR`
  env(F26 패턴, daemon이 아니라 콘솔 프로세스 env)를 검사 — supervisor가 아니면 트리 대신 일반 거부 문자열
  반환(supervisor 미언급). `parser.ts`/`mcp-server.ts`의 `/codebase` 설명도 normal 노출 최소화에 맞게 보정.
  - **주의**: `steer-handler.ts`는 콘솔(opencode 포크) 측 코드이므로 `process.env.AUTOSTOCK_SUPERVISOR`로
    프로필 판정 가능(launcher가 supervisor일 때만 `"on"` 설정, normal은 삭제 — config.ts:206-207). fail-closed:
    env 부재/`!=="on"` → 거부(SECURITY-15).

### 3.3 영향 파일 (확정 후보)
- 신규 `operator-console/cli/.autostock/operator.md`, `.autostock/normal-guard.md`
- `operator-console/launcher/config.ts` — `consoleEnv`에 `OPENCODE_CONFIG_CONTENT`(instructions) 프로필별 주입
- `operator-console/src/steer-handler.ts` — `verb==="codebase"` supervisor 게이팅(fail-closed)
- `operator-console/src/mcp-server.ts`, `operator-console/src/parser.ts` — `/codebase` 설명/노출 보정(필요 시)
- 테스트: launcher 테스트(`operator-console/test/launcher.test.ts`)에 프로필별 instructions 주입 검증 추가;
  steer-handler `/codebase` 게이팅 테스트(normal 거부 / supervisor 통과); `verify-lockdown.ts`/registry 회귀.

## 4. Construction 순서 (worktree feat/F39)
1. worktree 생성: `git worktree add .claude/worktrees/F39 -b feat/F39` (Code Gen Part 2 첫 동작).
2. 운영자 instruction 파일 2개 작성(§3.1 규칙).
3. launcher `config.ts` — 프로필별 `OPENCODE_CONFIG_CONTENT.instructions` 주입 + supervisor 분기.
4. `steer-handler.ts` `/codebase` supervisor 게이팅(fail-closed) + parser/mcp-server 설명 보정.
5. 테스트 작성/갱신 + 빌드(tsgo) + `verify-lockdown`/registry 회귀.
6. AGENTS.md 자동 로드 간섭 확인 및 정리.
7. **`/critic`** 어드버서리얼 리뷰(별도 컨텍스트) → 유효 지적 반영.
8. Build & Test 요약 + 머지 준비.

## 5. Extension 준수
- **Security Baseline (Enabled)**: SECURITY-03(거부/트리 메시지에 비밀·경로 노출 금지),
  SECURITY-15(`/codebase` 게이팅 fail-closed). 노출 표면 축소 변경 — 새 비밀 노출 없음.
- **PBT (Disabled)**: 알고리즘 로직 없음.
