# F26 — Supervisor Mode 요구사항

> Track: **F26** · Type: feature · Brownfield · Depth: Standard
> Source answers: `supervisor-mode-questions.md` (Q1–Q10, 2026-06-01)
> Security Baseline: **ENABLED** (Q7) · Property-Based Testing: **DISABLED** (Q9)

## 1. 의도 분석 (Intent Analysis)

- **User Request**: operator console 에이전트에 "supervisor mode"를 추가. supervisor에서는 autostock **전체 코드를 읽어** 자기 동작(예: "research turn에서 일어나는 일")을 근거 있게 설명할 수 있어야 한다. **수정은 금지**(자기파괴적). normal mode에서는 코드 접근을 차단하고 MCP 도구 + 권한 있는 파일 + 일반 웹 도구만 쓴다.
- **Request Type**: New Feature (권한/모드 레이어)
- **Scope**: Multiple Components — opencode 포크(서브모듈)의 권한/툴 레지스트리 + 런처(parent repo) + TUI 배지. 데몬 파이썬은 **불변**.
- **Complexity**: Moderate — 코드량은 적으나 보안 경계·런치 게이트·lockdown 정책을 정확히 다뤄야 함.

## 2. 현재 상태 근거 (코드 확인)

- 런처 `operator-console/launcher/config.ts:104-112`의 `consoleEnv()`가 콘솔에 `AUTOSTOCK_ROOT`(상위 레포 절대경로) + `AUTOSTOCK_LOCKDOWN=on`을 주입한다. 콘솔 cwd = `operator-console/cli`.
- 상위 레포 코드 읽기는 **`external_directory` 권한**으로 차단됨(`opencode.json`이 `"*": "deny"`; allowlist 미포함 → 거부). external-directory 검사: `packages/opencode/src/tool/external-directory.ts` + `project/instance-context.ts`(프로젝트 dir/worktree 안이면 통과).
- `registry.ts`(lockdown)는 `AUTOSTOCK_LOCKDOWN=on`일 때 edit/write/bash/task/fetch/patch/search 등 **부작용 빌트인을 컴파일에서 제거**. read/glob/grep/lsp + MCP만 생존 → **읽기 전용·수정 불가가 이미 구조적으로 보장**됨.
- 운영 상태 파일: `$STEERING_DIR/`(monitor.json·snapshot.json·commands·events·pending) / `workspace/`(turns·decisions·agent_questions·human_directives) / `logs/autostock.log`. **데몬이 publish_monitor/publish_snapshot로 후자들을 `$STEERING_DIR/`로 집계**(runtime.py:333-350, secret 마스킹). 콘솔 에이전트는 집계 뷰/`steer_read` MCP를 읽음.

## 3. 기능 요구사항 (Functional Requirements)

### FR-1 — 두 권한 프로파일, 런치 시점 결정 (Q1=B, Q2)
- supervisor 진입은 **`autostock --supervisor` 런치 플래그가 유일한 경로**. TUI 토글/`@멘션`/런타임 전환 **없음**.
- 플래그가 **세션 전체의 권한 프로파일**을 결정한다. 같은 에이전트지만 supervisor = normal의 **상위집합**. 플래그 없이 실행하면 normal 권한만.
- **메커니즘 요구 (critic HIGH#2, 코드 확인)**: 프로파일 분기는 **신규 구현**이다 — 현재 권한은 정적 `opencode.json` 1개 → `fromConfig`(파일 전용, `permission/index.ts:288`)에서만 오고, env→권한 코드는 없다(`AUTOSTOCK_SUPERVISOR` 참조 0). 또 런처 `cli.ts:56-57`은 `process.argv`를 **무가공 전달**해 `--supervisor`가 opencode로 누수된다. 따라서:
  - (a) 런처가 `--supervisor`를 **consoleArgs에서 소거**하고 `AUTOSTOCK_SUPERVISOR=on` env만 세팅(FR-4② 게이트).
  - (b) opencode 측에 **env→권한 주입 지점 신설**(config 로드 시 `AUTOSTOCK_SUPERVISOR`/`AUTOSTOCK_LOCKDOWN` + 환산된 절대경로로 `read`/`glob`/`grep`/`lsp`/`external_directory` 규칙을 normal/supervisor로 생성). "정적 JSON 하나"로는 두 프로파일이 불가 — Application Design R4의 확정 결론.

### FR-2 — Normal 프로파일 (기본)
- **허용**: 모든 `autostock_*` MCP 도구(읽기=`allow`, 쓰기성=`ask`, 현행 유지) + **웹 도구**(아래 FR-5).
- **파일 읽기**: read/glob/grep/list/lsp는 **`$STEERING_DIR/**` 한 디렉터리로만 제한**(운영 상태 파일). cli·python **소스 코드 읽기 전면 차단**(Q5=A). 상위 레포 `external_directory` 거부 유지.
  - **차단 대상에 cwd 자체 포함(중요)**: `Read .`/디렉터리 나열 등 **현재 프로젝트 디렉터리(=`operator-console/cli`) 내부 읽기도 차단**해야 한다. ⚠️ `external_directory` 권한은 "프로젝트 dir **바깥**"만 게이트하므로(`instance-context.ts`: 프로젝트/worktree 안이면 통과) cwd 내부 나열은 그것만으론 막히지 않는다.
  - **DESIGN-NOTE-1 — 채택 방식 (1) 경로-스코프, 검증 완료** (사용자 승인 2026-06-01):
    - `read`: **기본 deny + `$STEERING_DIR` allow**(경로-스코프). 검증: `read.ts:227`이 대상 경로를 `patterns`로 권한 평가하므로 `Read .`(cwd)·소스 파일 읽기가 deny로 차단됨. ⚠️ read 패턴은 **worktree-상대 경로**(`path.relative(instance.worktree, filepath)`)로 평가되므로, 런치 시점에 steering 절대경로를 worktree 기준으로 환산해 글롭을 생성하거나 `expand()`를 확장(`$STEERING_DIR` 해석)한다(현재 `expand()`는 `~`/`$HOME`만 처리).
    - `glob`/`grep`: normal에서 **전면 deny**. 이유: 이들은 권한 키를 "검색 패턴"으로 평가(`glob.ts:33`/`grep.ts:46`)하고 경로 한정은 `external_directory`에 의존하는데, cli는 worktree **내부**라 external_directory가 통과 → 경로 스코프가 불가. normal에선 소스 탐색이 불필요하므로 끈다(steering JSON은 `read`로 충분).
    - `lsp`: normal에서 deny(소스 대상 코드 인텔리전스).
    - `external_directory`: normal에서 기본 deny + **`$STEERING_DIR` 경로만 allow**(steering은 cli worktree 밖이라 read하려면 이 allow가 함께 필요). 단 `external_directory`는 **절대경로 dir**로 평가됨(external-directory.ts:31-34) — read의 worktree-상대 좌표계와 **다름**에 주의(아래 critic 보정 ③).
    - supervisor에선 `read`/`glob`/`grep`/`lsp` + `external_directory`를 `$AUTOSTOCK_ROOT` 대상으로 allow하되 비밀은 deny(글롭 형식은 critic 보정 ① 참조).
    - (대안 (2) cwd 이전은 미채택.)

  - **DESIGN-NOTE-1 보정 (critic 검토, 코드 확인 2026-06-01)** — 위 방식이 "실제로 동작"하려면 아래를 반드시 지킨다:
    - **① 비밀 deny 글롭은 worktree-상대 + dotall anchored 매칭에 맞춰야 함 (HIGH, 보안)**: `Wildcard.match`(`packages/core/src/util/wildcard.ts:13`)는 `^pattern$`(dotall) 정규식이고, supervisor가 상위 레포 비밀을 읽을 때 read 평가 패턴은 `../../.env`처럼 `../`로 시작한다. 따라서 `.env*`/`secrets`/`logs/`는 **매치 실패** → deny 무발동. 반드시 `**/`-접두 형태로: `**/.env*`, `**/secrets/**`, `**/*.key`, `**/*.pem`, `**/logs/**`, `**/.git/**`. 실측: `match("../../.env","**/.env*")=true`, `match("../../logs/x","**/logs/**")=true`.
    - **② deny 규칙이 allow보다 뒤에 와야 이긴다 (HIGH)**: `evaluate`는 `findLast`(`packages/core/src/permission.ts:25`)다. 룰 순서 = `{allow(허용 글롭) … 그 다음 deny(비밀 글롭)}`. 또한 `read` 룰의 **마지막**이 `{"*":"deny"}`가 되면 `disabled()`(`permission.ts:37-44`)가 read 도구를 통째로 제거해 steering조차 못 읽는 자가당착 → read는 `{"*":"deny", "<allow-glob>":"allow"}` 순서(allow가 마지막)로, glob/grep만 `{"*":"deny"}`(도구 제거 의도)로.
    - **③ `$STEERING_DIR`/`$AUTOSTOCK_ROOT` 글롭 주입 (MEDIUM)**: `expand()`(`permission/index.ts:280-286`)는 `~`/`$HOME`만 치환 → 두 변수는 리터럴로 남아 매치 불가. 그리고 read는 worktree-상대로 평가하므로 **런치 시점에 worktree 기준 상대 글롭으로 환산**해 규칙에 주입한다(절대경로를 그대로 넣으면 안 됨). `external_directory`는 절대경로 좌표계라 별도로 절대 글롭을 준다 — 두 좌표계를 분리해 설계.
    - **④ 검증 보강**: `verify-lockdown.ts`는 현재 패턴 `"*"`만 평가(`verify-lockdown.ts:17`)라 이 경로 버그를 못 잡는다 → 경로 케이스(`../../.env` deny, `../../<steering>/monitor.json` allow, normal에서 `.`(cwd) deny)를 단언에 추가.
- **쓰기/실행 빌트인**: edit/write/bash/task/patch 제거 유지(lockdown).
- **배지**: 없음.

### FR-3 — Supervisor 프로파일 (`--supervisor`)
- Normal의 모든 것 **＋ 코드 읽기 확장**: read/glob/grep/lsp가 **`$AUTOSTOCK_ROOT/**`(서브모듈 포함)** 까지 허용. external_directory를 AUTOSTOCK_ROOT로 스코프해 허용.
- **읽기 제외(차단) 글롭**(Q4=A): `.env*`, `secrets/`(및 `**/secrets/**`), `*.key`, `*.pem`, `logs/`(및 `**/logs/**`), `.git/`. 그 외 소스/문서/설정은 허용.
- **MCP 쓰기 도구**: normal과 동일하게 사용 가능(Q3=B), human-gated `ask` 유지.
- **쓰기/실행 빌트인**: **여전히 제거**(읽기 전용 보장; 자기수정 불가). supervisor라고 해서 edit/write/bash를 절대 추가하지 않는다.
- **배지**: TUI에 **`MODE: SUPERVISOR`** 표시(Q6=A; supervisor일 때만).

### FR-4 — 개발자 전용 진입 게이트 (Q8=A = ①+②)
- **①(구조적)**: 모델이 런타임에 프로파일을 바꿀 수 있는 도구가 **존재하지 않는다**. 프로파일은 프로세스 기동 시 플래그로 고정. `task` 제거로 subagent 경유 권한 상승도 불가. 권한을 바꾸는 MCP 도구 없음.
- **②(런치 게이트)**: `--supervisor`는 머신 셸 접근이 있어야 전달 가능. 런처는 사람이 플래그를 줄 때만 supervisor env를 세팅. 데몬/자율 경로가 띄우는 콘솔은 플래그를 **절대 넘기지 않으므로** supervisor 프로파일이 구조적으로 도달 불가.
- 비밀 토큰 게이트(B/D)는 채택하지 않음 — ①+②로 로컬 단일 개발자 환경엔 충분.

### FR-5 — 웹 도구 (Q10=B, 부속 a)
- **websearch + webfetch 모두 활성화**(임의 URL fetch 포함). lockdown이 현재 이들을 컴파일 제거하므로, **normal·supervisor 양쪽 프로파일에서 이 두 도구는 제거 대상에서 제외**(되살림)한다. edit/write/bash/task/patch는 계속 제거.
- 유출(exfiltration) 위험은 의식적으로 수용 — AR-1(§6) 참조.
- **websearch 활성화 (확정, 사용자 결정 2026-06-01 — 재논의 후)**: websearch는 자주 쓰므로 **기본 활성**한다. opencode는 `websearch`를 provider-gate하지만(`registry.ts:77` `webSearchEnabled` → `opencode` provider이거나 exa/parallel 플래그), 게이트 플래그는 env `OPENCODE_ENABLE_EXA`/`OPENCODE_ENABLE_PARALLEL`에서 온다(`effect/runtime-flags.ts`). 또 Exa 백엔드(`mcp.exa.ai/mcp`)는 **키 없이 동작**한다(`tool/mcp-websearch.ts:4-6`).
  - **구현**: 런처 `consoleEnv()`가 `OPENCODE_ENABLE_EXA="true"`를 주입(`AUTOSTOCK_LOCKDOWN`과 동일 패턴) → provider 무관 websearch 노출, 추가 키 불필요. 운영자가 `OPENCODE_ENABLE_PARALLEL`/`OPENCODE_ENABLE_EXA`를 직접 설정했으면 덮어쓰지 않음. `.env`의 `EXA_API_KEY`가 있으면 consoleEnv가 그대로 전달해 Exa 한도 상향에 자동 사용.
  - **잔여 위험**: 검색 질의가 제3자(Exa/Parallel)로 나가는 egress(AR-1 범주, 수용). 키리스 Exa는 레이트리밋 가능 — 헤비 유저는 `EXA_API_KEY` 권장.

### FR-6 — 운영 상태 파일 구조 (Q10-b 확답)
- 운영자-대면 상태는 **이미 `$STEERING_DIR/`로 집계**되어 있어 normal allowlist를 단일 디렉터리로 둘 수 있다. **이번 트랙에서 consolidation 리팩토링 불필요**(확답).
- 단서: 만약 향후 normal 모드에서 raw `workspace/`·`logs/` 파일을 **직접** 읽어야 하는 요구가 생기면, 그때는 흩어진 구조를 한곳으로 모으는 리팩토링이 필요하다(현재는 데몬 집계 + `steer_read`로 충분하므로 불필요).

### FR-7 — Fail-closed 기본값 (SECURITY-15)
- 플래그 부재/미상 → **normal**. supervisor인데 `AUTOSTOCK_ROOT`가 해석 불가 → 외부 읽기 거부(normal로 강등), 절대 fail-open 하지 않음.

## 4. 비기능 요구사항 (NFR)

- **NFR-1 (데몬 불변)**: 파이썬 매매 데몬 동작/계약은 변경 없음. 변경 표면은 포크(서브모듈) + 런처 + TUI에 한정.
- **NFR-2 (방어 검증 갱신)**: `verify-lockdown.ts` / `registry.test.ts`를 두 프로파일에 맞게 갱신 — supervisor에서도 edit/write/bash/task/patch가 `deny`/부재임을, normal에서 소스 읽기가 차단됨을, web 도구가 의도대로 켜짐을 단언.
- **NFR-3 (관측성, SECURITY-03/14)**: supervisor 진입을 로그로 남기되 비밀은 마스킹. 로그는 supervisor 읽기 범위에서 제외(FR-3)되어 자기 로그 열람·유출 방지.
- **NFR-4 (TUI 무영향)**: 소스 읽기 차단은 LLM 파일 도구(read/glob/grep)에만 적용 — TUI 클라이언트 자체 설정 로딩에는 영향 없음.

## 5. 보안 컴플라이언스 요약 (Security Baseline, ENABLED)

| Rule | 상태 | 근거 |
|---|---|---|
| SECURITY-06 Least privilege | **적용** | 프로파일별 최소권한: normal=steering dir만, supervisor=AUTOSTOCK_ROOT−비밀. 와일드카드 egress는 AR-1로 문서화된 예외. |
| SECURITY-08 App access control | **적용** | 개발자 전용 진입(FR-4): 런치 게이트 + 런타임 전환 도구 부재. |
| SECURITY-11 Secure design / defense-in-depth | **적용** | lockdown(컴파일 제거) + 권한 deny + 프로파일 스코프 다층. 오남용 시나리오(자가 권한 상승·exfil) 설계 반영. |
| SECURITY-15 Fail-safe defaults | **적용** | FR-7 fail-closed(기본 normal, 경로 미상 시 거부). |
| SECURITY-03 App logging (no secrets) | **적용** | 진입 로깅 + secret 마스킹(기존 `_mask_secrets`); 읽기 범위에서 `logs/` 제외. |
| SECURITY-13 Data integrity / audit | **적용** | 트랙 audit append-only; 코드 수정 도구 부재로 무결성 보존. |
| SECURITY-01/02/04/05/07/09/10/12/14 | **N/A** | 데이터스토어·LB/CDN·웹 HTML 엔드포인트·API 입력·네트워크 SG·인증/세션·SBOM 등은 본 트랙(로컬 권한/모드 설정)과 무관. (단 의존성 lockfile은 기존 유지.) |

## 6. 수용된 위험 (Accepted Risks)

- **AR-1 (Q10=B, webfetch egress)**: 임의 URL `webfetch`를 두 프로파일에서 허용 → 파일을 읽을 수 있는 세션이 외부로 데이터를 유출할 통로가 생김. **수용 근거**: (1) 단일 개발자 로컬 환경, (2) supervisor는 개발자 셸 기동에서만 도달(FR-4), (3) 최고가치 비밀(`.env`·`secrets`·`*.key`·로그)은 supervisor 읽기 범위에서 **이미 제외**(FR-3)되어 exfil 가치가 크게 감소. 사용자에게 위험을 명시 고지 후 의식적으로 채택.
  - ⚠️ **AR-1의 완화 (3)은 DESIGN-NOTE-1 보정 ①(올바른 `**/`-접두 deny 글롭 + deny-마지막 순서)이 구현·테스트되어야만 성립한다.** 글롭을 잘못 쓰면 비밀이 읽혀 exfil 위험이 완화되지 않으므로, 비밀-제외 경로 테스트는 **blocking**으로 다룬다(SECURITY-06/11).

## 7. 범위 밖 / 가정 (Out of Scope / Assumptions)

- 데몬·전략·리스크·브로커 로직 변경 없음.
- 비밀 토큰 기반 supervisor 게이트(Q8 B/D) 미채택.
- 가정: 소스 읽기 차단이 TUI 정상 동작을 깨지 않음(NFR-4) — Application Design에서 검증.
- 가정: lockdown에서 web 도구만 선택적으로 되살리고 edit/write/bash/task/patch는 제거 유지가 `registry.ts`에서 가능(설계에서 정확 지점 확정).

## 8. 핵심 요구사항 요약

- 권한 프로파일 2종을 **런치 플래그**로 선택(FR-1). normal=MCP+웹+`$STEERING_DIR/**`만(FR-2), supervisor=거기에 `$AUTOSTOCK_ROOT` 코드 읽기(비밀 제외) 추가(FR-3).
- 수정 도구는 어느 프로파일에서도 추가하지 않음(구조적 read-only).
- 개발자 전용은 **런치 게이트 + 런타임 전환 도구 부재**로 보장(FR-4), fail-closed(FR-7).
- 웹 search+fetch 활성(FR-5, 위험 AR-1 수용), supervisor 시 `MODE: SUPERVISOR` 배지(FR-3).
- 운영 상태는 이미 `$STEERING_DIR/`로 집계되어 consolidation 불필요(FR-6 확답).
