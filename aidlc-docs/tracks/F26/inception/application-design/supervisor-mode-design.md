# F26 — Supervisor Mode 애플리케이션 설계

> Track F26 · 요구사항 `requirements/supervisor-mode.md`(승인) · 계획 `plans/supervisor-mode-execution-plan.md`(승인)
> 모든 코드 인용은 검증됨(critic 교차확인). 이 문서가 R4(프로파일 선택 메커니즘)의 확정 결론이다.

## 0. 설계 한 줄 요약
런처가 `--supervisor` 유무로 **프로파일별 권한 JSON을 `OPENCODE_PERMISSION` env로 주입**하고, 포크는 (a) lockdown에서 web 도구만 복원, (b) sidebar에 배지를 그린다. opencode 권한 엔진/`fromConfig`는 **패치하지 않는다**(기존 env→권한 병합 경로 사용).

## 1. 두 레버 (코드 확정)

### 레버 A — web 도구 복원 (FR-5), 포크 `registry.ts`
- `lockdown`일 때 `builtin = readOnly`(`registry.ts:296`). `readOnly`(`:265-271`)에 **`tool.fetch` 추가 + `tool.search`는 `webSearchEnabled` 게이트(`:77`, provider 의존) 하에 추가**. edit/write/task/patch는 배열 미포함 → **계속 부재**(FR-4① read-only 유지, critic LOW 확인).
- 권한 측: `opencode.json`에 `"webfetch":"allow"`, `"websearch":"allow"` 추가(두 프로파일 공통, 정적). (스키마상 web 키는 `Action`만 — `config/permission.ts:28-29`.)

### 레버 B — 프로파일 권한 주입 (R4 확정), 런처
- `core/src/flag/flag.ts:67` → `process.env["OPENCODE_PERMISSION"]`. `config.ts:744-746`이 이를 `mergeDeep(result.permission, JSON.parse(env))`로 병합(remeda; source가 conflict 시 우선).
- **opencode.json은 프로파일-불변 정적 규칙만**: `"*":"deny"` + 모든 `autostock_*` MCP(현행) + `webfetch/websearch:"allow"`. **`read`/`glob`/`grep`/`lsp`/`external_directory`는 opencode.json에서 제거** → 이들은 전부 `OPENCODE_PERMISSION`이 공급(병합 충돌/순서 모호 제거; 순서를 launcher 단일 지점에서 통제).
- 런처(`launcher/cli.ts`)가 `--supervisor`를 **consoleArgs에서 소거**(현재 `:56-57` 무가공 전달 → 누수, 반드시 파싱), `consoleEnv()`(`config.ts`)에 `AUTOSTOCK_SUPERVISOR` + 계산된 `OPENCODE_PERMISSION`을 세팅.

## 2. 권한 규칙 (정확한 JSON, 순서 포함)

매처 사실(검증): `Wildcard.match`(`core/util/wildcard.ts:13`)는 `^pat$` dotall, `*`·`**` 모두 `.*`. `evaluate`(`core/permission.ts:25`)는 **findLast**(마지막 매칭 승). `disabled()`(`:37-44`)는 어떤 도구의 **마지막 매칭 룰이 `{"*":"deny"}`면 그 도구를 레지스트리에서 제거**.

좌표계(중요): `read`/`glob`/`grep` 권한 평가 패턴은 **worktree-상대**(`read.ts:229` `path.relative(instance.worktree, filepath)`; 콘솔 worktree=`operator-console/cli`). `external_directory`는 **절대경로**(`external-directory.ts:31-34`). 런처가 둘 다 계산(절대경로 보유).

상대경로 상수(런처 계산): cli worktree 기준 `STEERING_REL = ../../steering`(또는 `path.relative(consoleCwd, STEERING_DIR)`), 부모 루트는 `../..`. 절대경로: `AUTOSTOCK_ROOT`, `STEERING_DIR`.

### Normal 프로파일 — `OPENCODE_PERMISSION`
```json
{
  "read":  { "*": "deny", "<STEERING_REL>/**": "allow" },
  "glob":  "deny",
  "grep":  "deny",
  "lsp":   "deny",
  "external_directory": { "*": "deny", "<STEERING_DIR_ABS>/*": "allow" }
}
```
- `read`: 기본 deny + steering만 allow(**allow가 마지막** → findLast로 steering 허용; cwd `.`·소스는 deny). `disabled()`는 read의 마지막 룰 pattern≠`*` → read 도구 유지.
- `glob`/`grep`/`lsp`: `{"*":"deny"}` → `disabled()`가 **도구 자체 제거**(우회 불가). steering JSON 몇 개는 `read`로 충분.
- `external_directory`: steering(=cli worktree 밖) 절대 글롭만 allow → 상위 레포·기타 외부 거부. (read allow와 함께여야 steering 읽힘.)

### Supervisor 프로파일 — `OPENCODE_PERMISSION`
```json
{
  "read":  { "*": "allow",
             "**/.env*": "deny", "**/secrets/**": "deny",
             "**/*.key": "deny", "**/*.pem": "deny",
             "**/logs/**": "deny", "**/.git/**": "deny" },
  "glob":  "allow",
  "grep":  "allow",
  "lsp":   "allow",
  "external_directory": { "*": "deny", "<AUTOSTOCK_ROOT_ABS>/**": "allow",
             "<AUTOSTOCK_ROOT_ABS>/.env*": "deny",
             "<AUTOSTOCK_ROOT_ABS>/secrets/**": "deny",
             "<AUTOSTOCK_ROOT_ABS>/logs/**": "deny",
             "<AUTOSTOCK_ROOT_ABS>/.git/**": "deny" }
}
```
- `read`: `"*":"allow"`가 cli-내부(`src/foo.ts`)와 부모(`../../src/...`)를 모두 매치(dotall `.*`). **비밀 deny는 allow 뒤**(findLast 승) — 보정 ①②. 비밀 글롭은 `**/`-접두(상대 `../../.env`도 매치; 검증 `match("../../.env","**/.env*")=true`).
- `external_directory`: 절대 좌표계로 AUTOSTOCK_ROOT allow + 비밀 deny(절대). read와 별도 좌표계(보정 ③).
- write/실행 빌트인은 레지스트리에서 부재 유지 → supervisor도 read-only.

### 잔여 위험 노트
- **AR-2(LOW, 신규)**: supervisor에서 `glob`/`grep`는 권한 키가 "검색 패턴"이라 경로 deny가 안 먹고 external_directory(AUTOSTOCK_ROOT allow)에만 의존 → `secrets/` 하위 **파일명/경로가 glob·grep 결과에 노출**될 수 있다(내용은 `read` deny로 보호). 단일 개발자 supervisor 한정이라 수용. 필요 시 후속에서 glob/grep ignore 글롭 추가.

## 3. 런처 변경 (`operator-console/launcher/`)
- `cli.ts`: `userArgs`에서 `--supervisor` 검출·**제거** → `consoleArgs`엔 비포함(누수 차단). 검출 결과를 `consoleEnv`에 전달.
- `config.ts` `consoleEnv()`: 기존(`AUTOSTOCK_ROOT`/`STEERING_DIR`/token/`AUTOSTOCK_LOCKDOWN`)에 더해
  - `AUTOSTOCK_SUPERVISOR = supervisor ? "on" : 미설정`,
  - `OPENCODE_PERMISSION = JSON.stringify(profile)` — 위 §2의 normal/supervisor 객체를 `cfg.autostockRoot`/`cfg.steeringDir`/`cfg.consoleCwd`로 글롭 채워 생성(상대·절대 둘 다). 순수 함수로 분리(`buildPermissionProfile(cfg, supervisor)`)해 단위테스트.
- 데몬/자율 경로는 `--supervisor`를 절대 넘기지 않음 → 항상 normal(FR-4②, FR-7 fail-closed).

## 4. TUI 배지 (`packages/opencode/src/cli/cmd/tui/feature-plugins/sidebar/autostock.tsx`)
- 위치 정정: `tui-trading` 아님(critic LOW). 이 파일은 이미 `process.env.STEERING_DIR`를 읽음(`:90,:102,:205`) → 동일 경로로 `process.env.AUTOSTOCK_SUPERVISOR === "on"`일 때만 `MODE: SUPERVISOR` 배지 렌더(FR-3/Q6/A). 평시 미표시.

## 5. 검증 (Build & Test, blocking 표시)
- **`verify-lockdown.ts` 확장 — blocking**: 현재 패턴 `"*"`만(`:17`). 두 프로파일의 `OPENCODE_PERMISSION`을 `fromConfig`로 평가해 **경로 케이스** 단언:
  - normal: `read .`(cwd `""`)=deny, `read <STEERING_REL>/monitor.json`=allow, `read src/x.ts`=deny, `glob`/`grep` 도구 부재(`disabled()`), `webfetch`=allow, edit/write/bash/task=deny.
  - supervisor: `read ../../src/strategy/llm/client.py`=allow, `read ../../.env`=**deny**, `read ../../logs/autostock.log`=**deny**, `read ../../secrets/x.key`=**deny**, edit/write/bash/task=deny(여전).
- `test/tool/registry.test.ts`: lockdown 시 `fetch`(+`search`) 추가·`edit/write/task/patch` 부재 단언(R2 회귀 방지).
- `launcher` 테스트: `buildPermissionProfile` 순수함수 normal/supervisor JSON 스냅샷; `--supervisor`가 consoleArgs에서 제거되고 env에 `AUTOSTOCK_SUPERVISOR=on`+`OPENCODE_PERMISSION` 세팅; 무플래그 시 normal.
- docker-verify attach: normal에서 `Read .` 거부 + supervisor에서 상위 레포 read 허용·`.env` 거부 수동 확인.

## 6. 영향/불변
- 데몬·파이썬 불변(NFR-1). 변경 = 포크 `registry.ts`+`opencode.json`+sidebar, 런처 `cli.ts`+`config.ts`. 서브모듈 `feat/F26` 브랜치, 부모 gitlink는 머지 시점.
- `fromConfig`/permission 엔진/`external-directory.ts`/`read.ts` **수정 없음** — 기존 동작 그대로 활용.

## 7. 구현 순서 (Code Gen)
1. 포크: `opencode.json`(정적 축소 + web allow) → `registry.ts`(readOnly에 fetch/search) → `registry.test.ts`.
2. 런처: `buildPermissionProfile()` + `consoleEnv()` 확장 + `cli.ts` 플래그 파싱 → launcher 테스트.
3. 포크: sidebar 배지.
4. `verify-lockdown.ts` 경로-케이스 확장.
5. 워크트리에서 typecheck/test 후 머지.
