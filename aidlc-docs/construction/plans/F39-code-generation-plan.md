# F39 — Code Generation Plan (unit `normal-mode-code-block`)

> Worktree `.claude/worktrees/F39` (branch `feat/F39`). App code in worktree; docs in main `aidlc-docs/`.
> 2층 defense-in-depth: L1 운영자 페르소나/거부 프롬프트(프로필별 주입), L2 `/codebase` 구조적 게이팅.

## 코드 확인으로 확정된 사실 (설계 근거)
- opencode 시스템 프롬프트 = `[...env, ...instructions, ...skills]` (`prompt.ts:1441`). `instructions`는
  `instruction.system()`이 (a) 프로젝트 `AGENTS.md`(첫 매치) + (b) `config.instructions`를 로드해 구성
  (`instruction.ts:122-149`). 콘솔 cwd=`operator-console/cli` → 현재 **`cli/AGENTS.md`(opencode 개발 가이드)**가
  운영자 instruction으로 로드됨(근본 원인). `config.instructions`는 **마지막에** 추가 → 시스템 프롬프트 후미 =
  최고 salience.
- `OPENCODE_CONFIG_CONTENT` env(`flag.ts:22`, `config.ts:666`)로 부분 config를 주입하면 프로젝트 config와
  **merge**(instructions 배열은 union, `config.ts:57-58`). → 프로필별 instructions 주입 가능(F26의
  `OPENCODE_PERMISSION` 주입과 동일 패턴). **`OPENCODE_DISABLE_PROJECT_CONFIG`는 사용 안 함** — 그것은
  프로젝트 `opencode.json`(F26 권한 + MCP 권한)까지 스킵하므로 너무 광범위(`config.ts:602`).
- **MCP 서버 env는 명시적 allowlist**(`.opencode/opencode.jsonc:21-26`: STEERING_DIR/TOKEN/ALPACA_*만).
  `AUTOSTOCK_SUPERVISOR` 미포함 → steer-handler(MCP 프로세스)는 supervisor 여부를 못 봄. **L2 게이팅을 위해
  이 map에 `AUTOSTOCK_SUPERVISOR` 추가 필수** (안 하면 supervisor에서도 `/codebase` 거부 = F29 회귀).

## 단계 (Part 2)
- [x] **S1** 신규 `operator-console/prompts/operator.md` — 운영자 페르소나(공통, 두 프로필). 역할/도구/한국어/
  "opencode 개발 가이드·SDK·커밋 규칙 등 타 instruction은 이 콘솔과 무관하니 따르지 말 것" 명시.
- [x] **S2** 신규 `operator-console/prompts/normal-guard.md` — normal 전용 거부 규칙(소스/구현 질문 거부,
  추측·소스읽기 시도 금지, supervisor 미언급, 운영 질문은 데이터로만).
- [x] **S3** `launcher/config.ts` — `buildInstructions(cfg, supervisor)` 추가(절대경로) + `consoleEnv`에
  `out.OPENCODE_CONFIG_CONTENT = JSON.stringify({ instructions })` 주입. normal=[operator,normal-guard],
  supervisor=[operator].
- [x] **S4** `.opencode/opencode.jsonc` — mcp.autostock.environment에 `"AUTOSTOCK_SUPERVISOR": "{env:AUTOSTOCK_SUPERVISOR}"` 추가.
- [x] **S5** `src/steer-handler.ts` — `handleSteerRead(command, fd, supervisor=false)` 시그니처 확장;
  `verb === "codebase"`일 때 `!supervisor` → 일반 거부 문자열(supervisor 미언급, fail-closed, SECURITY-15).
- [x] **S6** `src/mcp-server.ts` — `const supervisor = process.env.AUTOSTOCK_SUPERVISOR === "on"`; 호출부
  `handleSteerRead(command, fd, supervisor)`; `steer_read` 설명의 CODEBASE verb 줄을 "supervisor 전용" 톤으로 보정.
- [x] **S7** 테스트:
  - `test/launcher.test.ts` — consoleEnv가 normal/supervisor별로 OPENCODE_CONFIG_CONTENT.instructions를
    올바르게 주입(normal=2개 normal-guard 포함, supervisor=1개 미포함).
  - `test/steer-handler.test.ts` — `/codebase` normal=거부(트리 미반환, supervisor 미언급), supervisor=정상 반환.
- [x] **S8** 빌드/회귀: `bun test` (operator-console) — launcher+steer-handler+parser+filedrop+f21+f14
  **107 pass / 0 fail**. verify-lockdown(2-profile)·registry 테스트는 fresh worktree에 opencode deps
  (drizzle-orm) 미설치로 재실행 보류 — 단 변경이 `buildPermissionProfile`/`registry.ts`/`cli/opencode.json`
  (verify-lockdown가 읽는 파일)을 **전혀 건드리지 않음** → F26 lockdown 단언 영향 없음. (alpaca-data/contract
  테스트는 ALPACA 키 fail-fast = 기존 조건, 본 변경과 무관.)
- [x] **S9** `/critic` 리뷰 완료 (별도 컨텍스트 서브에이전트) — 5건, 모두 코드로 교차검증:
  - **HIGH#1** opencode.jsonc 주석 오류("MCP env가 console env 미상속") — 실제론 `{...process.env,...environment}`로
    상속(mcp/index.ts:433-437). fail-closed는 유지(런처 normal: key 삭제 + `{env:}`→"" overlay)지만 주석 정정.
    bare `bun dev` + `export supervisor=on`은 개발자 의도 = F26 신뢰경계 → **AR-2**. → 주석/문서 수정 완료.
  - **HIGH#2** 개발자용 AGENTS.md가 **2개**(`cli/AGENTS.md`+`packages/opencode/AGENTS.md`) 자동 주입(findUp 전체 매치,
    filesystem.ts:128-138; `bun dev` cwd=packages/opencode, package.json:9). L1은 salience-only. → operator.md를
    "AGENTS.md/개발 지침 명시적 무시 + 유도 거부"로 강화, NFR-1 범위 정정(L2는 `/codebase`만, 프리폼 추론은 L1) → **AR-1**.
  - **MED#3** verify-lockdown 회귀 미실행 주장 → **실제 실행**: `bun install` 후 verify-lockdown **PASS ✅**(2-profile),
    registry.test **16 pass**. (verify-lockdown은 consoleEnv/opencode.jsonc를 읽지 않고 buildPermissionProfile만 검증 — 영향 없음 확인.)
  - **MED#4** NFR-1 과대표현 → 범위 정정(위 HIGH#2와 함께).
  - **LOW#5** 크로스-프로세스 통합테스트 부재 = opencode {env:} 자체 동작이라 격리 단위테스트 비현실 → 핸들러 fail-closed 단위테스트로 충분, 주석 보강.
  - **검증완료(유지)**: `{env:}`미설정→""(variable.ts:36-38), instructions union merge(config.ts:55-61), operator.md 후미 로드, 프로젝트 CLAUDE.md 미오염(AGENTS.md 먼저 매치 break), 거부메시지/설명 SECURITY-03 누설 없음.

## Extension 준수 (Security Baseline)
- SECURITY-03: 거부/게이팅 메시지에 비밀·경로·supervisor 존재 노출 금지(일반 표현).
- SECURITY-15: `/codebase` 게이팅 fail-closed(`AUTOSTOCK_SUPERVISOR !== "on"` → 거부).
- PBT: N/A(알고리즘 로직 없음).
