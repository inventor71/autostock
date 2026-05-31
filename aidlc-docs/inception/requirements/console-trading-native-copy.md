# F7 — 콘솔 트레이딩-네이티브 카피 & 팁 (Requirements)

> **트랙**: F7 / **단계**: INCEPTION → Requirements Analysis (minimal depth)
> **상태**: 작성 완료 — 승인 대기
> **기반**: F5의 리브랜딩된 콘솔 포크(`operator-console/cli`, opencode hard-fork, main 머지됨)
> **작성일**: 2026-05-30

## 1. 배경 / 의도

F5에서 콘솔의 **로고·타이틀·resume 안내·wordmark**까지는 트레이딩-네이티브로 리브랜딩했으나,
홈 화면의 **프롬프트 placeholder**와 **회전 팁(rotating tips)** 카피는 여전히 opencode의
*코딩 도구* 문맥("Fix a TODO", "opencode run -f file.ts", "agent create", github PR 등)에 머물러 있다.
이는 트레이딩-스티어링 콘솔로서 off-brand이며, F5에서 사용자 결정으로 F7로 분리(carve-out)되었다.

F7은 **카피(문구) 전용** 작업이다. 기능 동작·경로·식별자·MCP 배선은 건드리지 않는다.

### 1.1 상호작용 모델 (정정 — 카피의 근거가 됨)

코드 확인 결과 (`operator-console/src/mcp-server.ts`, `steer-handler.ts`, `cli/.../tool/registry.ts:60`,
포크 TUI에 스티어링 verb의 `registerCommand` 없음):

- 콘솔은 opencode-fork **LLM 에이전트와의 대화**다. 운영자는 **자연어로 의도를 말한다**("sell half my AAPL").
- `/buy`·`/pause`·`/approve`·`/status` 등의 `/verb` 문법은 **`autostock_steer`(변이) / `autostock_steer_read`(읽기)
  MCP 툴의 `command` 인자 형식**이다 — 툴 description으로 LLM에 노출됨. **opencode TUI의 슬래시 명령으로 등록돼
  있지 않다.** 운영자가 프롬프트에 직접 타이핑하는 콘솔 명령이 아니다.
- 콘솔의 **유일한 변이 능력** = `autostock_steer` MCP 툴. 변이 명령은 opencode CORE가 실행 전 **사람 confirm을
  자동 요청**(permission `"ask"`); 읽기 verb는 무게이트(`"allow"`). 최종 안전장치는 daemon `RiskManager`.
- break-glass = Alpaca UI 직접 개입(+ reconcile로 에이전트가 인지). lockdown = 부수효과 builtin 전부 컴파일 아웃,
  read-only + `autostock_steer` 만 노출.

**카피 함의**: placeholder/팁은 운영자가 **자연어로 의도를 말하면 에이전트가 제안하고 opencode가 확인을 요청한다**는
모델을 가르쳐야 한다. "`/approve`를 실행하라"처럼 **타이핑하는 콘솔 명령으로 오해시키면 안 된다.** `/verb` 문법은
필요 시 "에이전트가 쓰는 명령 어휘(정밀 지시 시 그대로 말해도 됨)"로 소개할 수 있으나, 주된 안내는 자연어다.

## 2. 범위 (In)

### FR-1. 홈 프롬프트 placeholder 교체
- 대상: `packages/opencode/src/cli/cmd/tui/routes/home.tsx`의 `placeholder.normal` / `placeholder.shell`
  (현재 `normal = ["Fix a TODO in the codebase", "What is the tech stack of this project?", "Fix broken tests"]`,
  `shell = ["ls -la", "git status", "pwd"]`).
- 결정 (Q2 = **자연어 위주**): `normal`을 자연어 스티어링 예시로 교체.
  예) `"sell half my AAPL"`, `"pause new entries"`, `"what are my open positions?"`.
  콘솔은 자연어(MCP `autostock_steer`)와 슬래시 명령을 모두 받지만, 헤드라인 가치(평어로 빠르게 개입)를
  강조하기 위해 placeholder는 자연어를 전면에 둔다.
- `placeholder.shell`은 실제 셸 입력 예시이므로 **기능적 의미가 있다** → 일반적인 쉘 예시 유지(변경 불필요/저우선).

### FR-2. 회전 팁 — 최소·외과적 교체
- 대상: `packages/opencode/src/cli/cmd/tui/feature-plugins/home/tips-view.tsx`의 `TIPS` 배열(~120개).
- 결정 (Q1 = **최소·외과적**):
  - **교체 대상 = 명백히 코딩/오픈코드-개발 전용이라 트레이딩 콘솔에서 off-brand인 팁만.** 예:
    `opencode run -f file.ts`, `opencode agent create`, `opencode serve/run --attach/upgrade`,
    github 연동(`/opencode`, `github install`, `/opencode fix this`, `/oc`), `/review`(코드 리뷰),
    `AGENTS.md` 팀 공유, `/init`(코드베이스 룰 생성), `docker run … opencode`, 코드 도구/플러그인 작성 안내 등.
  - **유지 대상 = 콘솔에서도 그대로 유효한 일반 TUI 팁** (단축키, `/new`·`/sessions`·`/compact`·`/themes`·
    `/models`, `@파일`, 사이드바 토글, 메시지 탐색 등) **및 실경로를 참조하는 config 팁**
    (`~/.config/opencode/...`, `.opencode/...`, `tui.json`, `mcp` 설정 등 — 실제 파일 경로이므로 보존).
- 교체된 자리에는 **트레이딩-스티어링 팁**을 넣는다(실제 명령 문법에 정확히 맞춤 — §5 참조).

### FR-3. 안전/거버넌스 팁 포함
- 결정 (Q3 = **포함**): 트레이딩 팁에 운영자 안전 모델을 가르치는 팁을 포함한다. **단, §1.1의 상호작용 모델대로
  자연어 의도 + confirm 게이트로 표현한다 — "명령을 타이핑하라"가 아니다.** 예시(자연어 중심):
  - 확인 게이트: "거래를 요청하면 opencode가 실행 전 한 번 더 확인을 요청한다 — 에이전트는 *제안*만 하고
    스스로 주문하지 못한다." (변이 = `autostock_steer` `"ask"` 자동 게이트)
  - 승인 흐름: "사람이 손댄 심볼에 에이전트가 매매하려 하면 보류(pending)된다 — 'approve the pending AAPL buy'/
    'reject it'처럼 말하면 에이전트가 처리한다." (내부 어휘: `/approve <id>` / `/reject <id>`)
  - 비상 정지: "'flatten everything', 'pause new entries', 'kill' 처럼 말해 즉시 멈출 수 있다."
    (내부: `/flatten all` · `/pause` · `/halt-entries` · `/kill`)
  - 읽기: "'show my positions', 'why did you buy NVDA?'는 확인 없이 바로 답한다." (읽기 = `autostock_steer_read` `"allow"`)
  - break-glass: "최후엔 Alpaca UI에서 직접 청산할 수 있고, reconcile로 에이전트가 그 변경을 인지한다."
  - lockdown/권한 분리: "콘솔의 유일한 변이 능력은 `autostock_steer` 한 가지다(셸/편집/쓰기 빌트인은 컴파일 아웃)."

### FR-2.1 (정정 2026-05-31) — 홈 팁 회전을 "트레이딩 우선"으로
사용자 결정: 회전 팁 풀이 일반 opencode 팁 ~100개에 압도되면 트레이딩 팁이 ~8%로만 노출됨 → **홈 팁 풀을
[트레이딩 9개 + 콘솔에서 실제 유용한 일반팁 ~8개]로 추리고 나머지는 홈 회전에서 제외**(딥한 opencode-dev/config/
github 팁). 이는 초기 Q1 "최소·외과적"에서 "트레이딩-우선 큐레이션"으로 진화한 결정. 실경로/실설정 자체는 코드/문서에
그대로 존재하며, 단지 홈 *팁 회전*에서만 빠진다.

### FR-3.1 (정정 2026-05-31) — 가볍게, "가능한 일" 위주
사용자 피드백: 안전/거버넌스 팁을 **매커니즘을 깊게 설명하지 말고 "무엇이 할 수 있는지" 위주로** 작성.
- confirm 게이트/권한분리/RiskManager 같은 내부 매커니즘은 한 줄짜리 안심 문구로 축약("주문은 실행 전 항상 확인을 거쳐요").
- 팁 개수도 ~12 → **~8–9개로 슬림화**, 한 팁 = 한 capability.

### FR-5 (신규 2026-05-31, rev2) — 로케일 인식은 "메인(placeholder)에만"
- **로케일 분기 대상 = 홈 프롬프트 placeholder(`placeholder.normal`)뿐.** 런타임 로케일이 한국어면 한글, 아니면 영어.
- **감지 방식**: 포크에 i18n 인프라가 없으므로 소형 헬퍼 신규 추가 —
  `(LC_ALL || LC_MESSAGES || LANG || Intl.DateTimeFormat().resolvedOptions().locale || "").toLowerCase().startsWith("ko")`.
- **팁은 영어 단일** (rev2, 사용자 정정): 회전 팁 풀에는 유지되는 일반 opencode 영어 팁(~100개)이 섞여 나오므로, 우리 팁만
  한글로 분기하면 한/영이 뒤섞여 일관성이 깨진다 → 신규 트레이딩 팁·`NO_MODELS_TIP`은 **영어로만** 작성(트레이딩-네이티브
  리브랜드는 유지, 로케일 분기는 안 함). "최소·외과적" 원칙과도 합치.

### FR-4. (선택·저우선) debug 라인
- `debug` 명령의 `opencode version:` 표기 등 디버그 전용 표시는 저우선. 시간이 남으면 다룬다.

## 3. 범위 (Out / 유지 — 기능이지 표시 브랜드가 아님)

- 실제 config 경로: `~/.config/opencode`, `opencode.json`, `.opencode/`
- 테마 id `"opencode"`, provider id, MCP `clientInfo`, `opencode` 바이너리 spawn(`pr.ts`), 패키지 매니저 이름
- 일부 팁이 정당하게 참조하는 실경로(`~/.config/opencode`)는 그대로 둔다.
- **기능 동작 일절 변경 없음** — 순수 문자열/카피 변경만.

## 4. 비기능 요구 (NFR)

- **NFR-1 (무결성)**: 카피 변경이 타입체크(`tsgo --noEmit`)와 기존 테스트를 깨지 않을 것. 팁의
  `{highlight}…{/highlight}` 마크업·`shortcuts` 콜백 시그니처·`Tip` 타입 계약을 보존.
- **NFR-2 (정확성)**: 모든 예시 명령/문구는 **실제 스티어링 문법과 일치**해야 한다(가공된 명령 금지).
  근거: `src/agent/steering/commands.py` 동사 집합(§5).
- **NFR-3 (보안, SECURITY-03)**: 팁/placeholder에 비밀·토큰·계정 식별자 노출 금지(예시는 일반적 심볼만).
- **PBT**: 본 단위에는 **N/A**(순수 카피, 검증 대상 순수 함수 없음).

## 5. 근거 — 실제 스티어링 어휘 (코드 확인)

**콘솔-노출 문법은 MCP 툴 description 기준**(`operator-console/src/mcp-server.ts`) — 운영자/LLM가 보는 형식이며,
하이픈 표기를 쓴다(daemon 내부 `commands.py`는 `halt_entries` 등 언더스코어; 파서가 매핑). 카피에는 **이 콘솔-노출
형식**을 쓴다. 모두 `autostock_steer`(변이, confirm=`"ask"`) / `autostock_steer_read`(읽기, `"allow"`) 툴의 `command` 인자다:

- 거래(변이): `/buy SYM N$|Nsh` · `/sell SYM N%|Nsh|N$` · `/flatten SYM` · `/flatten all` · `/stop SYM PRICE`
- 라이프사이클(변이): `/pause` · `/resume` · `/halt-entries` · `/allow-entries` · `/kill`
- 승인(변이): `/approve ID` · `/reject ID` (대상은 `snapshot.pending`)
- 취소(변이, 인자로 의미 구분): `/cancel SYM`(저항성 보호주문 취소) · `/cancel ID`(대기 중 off-hours 거래 삭제)
- 기타(변이): `/unlock SYM` · `/note TEXT` · `/directive TEXT` · `/directive-clear ID` · `/answer ID TEXT`
- 읽기(`steer_read`, 무게이트): `/status` · `/positions` · `/orders` · `/book` · `/agent-trace` · `/why`
  · `/turns` · `/decisions` · `/log`
- **운영자 주 경로 = 자연어** → 에이전트가 위 문법으로 `autostock_steer` 호출 → opencode가 confirm 요청.
  콘솔의 유일한 변이 능력(`tool/registry.ts:60`); 스티어링 verb는 **TUI 슬래시 명령으로 등록돼 있지 않음**.

## 6. 수용 기준 (Acceptance Criteria)

- [ ] AC-1: `home.tsx`의 `placeholder.normal`이 자연어 스티어링 예시로 교체됨.
- [ ] AC-2: `tips-view.tsx`에서 명백히 코딩 전용인 팁이 트레이딩-스티어링 팁으로 교체됨;
      일반 TUI 팁·실경로 config 팁은 보존됨(최소·외과적).
- [ ] AC-3: 교체된 팁 집합에 안전/거버넌스 팁(승인 흐름·비상정지·break-glass·lockdown)이 포함됨.
- [ ] AC-4: 모든 예시 명령/verb가 §5의 콘솔-노출 문법과 일치(가공 명령 0건).
- [ ] AC-5: `tsgo --noEmit` 클린 + 기존 launcher/console 테스트 그린(무회귀).
- [ ] AC-6: 기능 경로/식별자/MCP 배선 무변경(diff는 카피 문자열에 한정).
- [ ] AC-7: 카피가 §1.1 상호작용 모델을 정확히 반영 — placeholder/팁은 자연어 의도 + opencode confirm 게이트로
      표현하고, 스티어링 verb를 "타이핑하는 TUI 명령"으로 오해시키지 않음.

## 7. 가정 / 제약

- 단일 소규모 단위; F5 베이스(콘솔 포크)에서 worktree로 작업, 머지는 사용자 승인 후.
- F6(사이드바 resize)와는 편집 파일이 겹치지 않음(F7 = `home.tsx`/`tips-view.tsx` 카피, F6 = 사이드바/index.tsx) → 충돌 없음.
- 빌드/타입체크는 사용자 머신/포크 환경에서 수행(F5와 동일 패턴: bun install + tsgo).

## 8. 확장(Extensions) 적용

- **Security Baseline = Enabled**: 적용 = SECURITY-03(로그/표시에 비밀 노출 금지, NFR-3). 그 외 대부분 N/A
  (웹앱·DB·IaC·인증 없음; 순수 카피).
- **Property-Based Testing = Partial**: 본 단위 **N/A**(검증할 순수 함수 없음 — 카피 전용).

## 9. 깊이 판정

**Minimal** — 의도 명확, off-brand 카피 교체라는 단일 목적, 위험 낮음(기능 무변경, 롤백 용이),
단일 소규모 단위. User Stories SKIP 권고(운영자 단일 사용자 도구, 워크플로는 FR로 포착 — F2/F3/F5와 일관).
