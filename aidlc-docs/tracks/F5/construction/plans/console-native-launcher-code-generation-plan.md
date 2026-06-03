# F5 Code Generation Plan (유닛 `console-native-launcher`)

- **승인 후 Part 2 자율 진행**(설계 승인 완료). 진짜 사람 판단(라이브 검증 / 원격 push 인증)에서만 정지.
- **신규 런타임 의존 0.** 안전 엔진/주문 경로/채널 계약 불변(BR-10/12). 파이썬 데몬 코드 변경 0 목표.
- 근거 설계: `nfr-design/{nfr-design-patterns,logical-components}.md`, `functional-design/*`.

## Step 0 — worktree + branch (critic2 #4) ✅
- [x] `git worktree add .claude/worktrees/console-native-launcher -b feat/console-native-launcher` (off `main`).
- [x] **worktree 안에서 서브모듈 체크아웃**: `git submodule update --init operator-console/cli` (확인: 신규 worktree에서 비어 있었음 — critic2 #4 검증).
- [x] **서브모듈을 실브랜치로**: `git -C operator-console/cli switch -c feat/console-native-launcher` (detached HEAD 회피).

## Step 1 — 런처 코어 (headless 테스트 가능, `operator-console/launcher/`)
- [ ] `config.ts` — `LauncherConfig`(E5): AUTOSTOCK_ROOT/STEERING_DIR/canonical token(root .env)/mcp path/install path 해석.
- [ ] `preflight.ts` — `PreflightCheck`(E1)/집계(E2): token_canonical·steering_dir·mcp_path(blocking) + remediation (P5). 토큰 값 미출력(P4/BR-6).
- [ ] `unit-template.ts` — systemd 유닛 텍스트 생성(WorkingDirectory/EnvironmentFile/ExecStart venv/Type=simple/Restart/Install) (P3, critic #4).
- [ ] bun unit tests: preflight 판정/집계, 토큰 canonical 해석/drift warn, 유닛 텍스트 생성.

## Step 2 — systemd 데몬 관리 (`launcher/daemon.ts`) ✅
- [x] **유닛 = `WorkingDirectory={ROOT}` + `load_dotenv()`만 authoritative (critic2 #3)**: `EnvironmentFile` 제거 (unit-template.ts).
- [x] `DaemonService`(E3): `is_active`/`ensure_installed`(daemon-reload+enable+linger, 멱등)/`ensure_running`(inactive→start 멱등 BR-9.1→health-wait; active→health만; failed→진단).
- [x] health-wait(P2, critic #1): snapshot `published_at` 전진 OR 연속 2회 신선; `health_window=45s`/`timeout=60s`/`poll=1s`; bare mtime 금지; wedged 진단.
- [x] bun unit tests: 상태 전이(mock systemctl), health-wait 판정(mock snapshot published_at). **20 launcher tests green.**

## Step 3 — 진입 오케스트레이션 + 설치 (`launcher/cli.ts`, `install.ts`) ✅
- [x] `cli.ts`(P1): resolveConfig→preflight→ensureDaemon→**launchConsole(exec 핸드오프)**; **종료코드 규약**(10/11/12/13) + 최상위 die→무진단 경로 0.
- [x] **TTY exec 핸드오프 (critic2 #1)**: 콘솔 = 파이프라인 마지막, `Bun.spawn(stdio:"inherit")` + `await exited` 전파 — **launcher-side watch 없음**.
- [x] **콘솔 env/cwd 완전 재현 (critic2 #2)**: `consoleEnv()`가 `AUTOSTOCK_ROOT`+`STEERING_DIR`+token+LOCKDOWN export, cwd=`operator-console/cli`에서 `bun run dev`.
- [x] `install.ts`(멱등): `~/.local/bin/autostock` 심(AUTOSTOCK_ROOT bake) + 유닛 생성/reload/enable/linger + PATH 미포함 경고(BR-15).
- [~] **MCP 가용성 사후 단언** — preflight의 `mcp_path`(파일 존재)로 1차 방어; 런타임 등록 단언은 S6 배너에 통합(라이브).
- [x] bun build clean (cli/install 번들 OK); **full console suite 45 green (무회귀).**

## Step 4 — 리브랜딩 (포크, P8/BR-14)
- [x] `cli/logo.ts` 글리프 → **2줄 스택 "auto"/"stock"** 작성(8행 left + 빈 right; 블록 글리프만; 렌더러 무변경). 커밋 `ea9a885`. **시각 미세조정 = 사용자 머신 빌드 후.**
- [x] `cmd/tui/app.tsx` 대문자 타이틀 "OpenCode"→"autostock", "OC |"→"AS |"(BR-14.2). 서브모듈 커밋 `241351a`. (검증: grep)
- [~] 노출 "opencode" 문자열 추가 치환(스플래시/about/팁 등) — **`item.id !== "opencode"` 제외**(BR-14.1); 렌더 확인 동반 → **라이브 루프**(빌드 시 남은 brand 문자열 식별·교체).
- [x] **tsgo 타입체크 클린(0 errors)** — 워크트리 포크에서 `bun install`(4706 pkg) 후 `tsgo --noEmit` 통과(logo.ts/autostock.tsx/app.tsx).

## Step 5 — 세션 우선 시작 (옵션 B) ✅(런처) / 라이브 검증 대기
- [x] 런처가 `bun run dev -- -c`로 세션 진입 플래그 전달(`cli.ts`). 기존 `sidebar_content` 경로 재사용.
- [~] **라이브 검증**: 켜자마자 세션 뷰 + autostock 사이드바, 입력/명령 무파손. 최근 세션 없을 때 `-c` 폴백 동작 확인.

## Step 5 — 사이드바 우선 / home-skip (포크, P6/BR-7) — ⚠ 정책 분기 대기 (critic2 #5)
> critic2가 입증: home은 중앙 컬럼이라 `sidebar_content` consumer가 없고(`session/sidebar.tsx:92`만 소비, 세션 게이팅
> `session/index.tsx:236`), 사이드바를 home에 얹는 건 **레이아웃 수술**이며 패널 snapshot 폴은 세션 컨텍스트가 필요.
> 라운드1의 "home에 슬롯(덜 침습)" 전제가 뒤집힘. 사용자 원래 Q1=A("바로 세션 뷰로")는 옵션 B에 가까움.
- **결정 = 옵션 B** (사용자 2026-05-30 "B로 하고 승인"; 원래 Q1=A 의도와 일치): 부팅 시 세션 라우트로 자동 진입
  (`-c` 최근 세션 or 합성 빈 세션) → **기존 `sidebar_content` 경로 그대로 재사용**(`auto&&wide` 게이팅 BR-7.2).
- [ ] 런처가 콘솔을 세션 진입 플래그(`-c` 등)로 기동하도록 배선(`cli.ts`); 최근 세션 없을 때 합성 세션 처리.
- [ ] **라이브 검증(사용자 머신)**: 켜자마자 세션 뷰 + autostock 사이드바, 입력/명령 무파손. (`-c` 동작/플래그 전달 방식 확정.)

## Step 6 — 런타임 끊김 배너 (포크, P7/E6/BR-8) ✅(코드) / 라이브 검증 대기
- [x] `sidebar/autostock.tsx`: 패널을 항상 렌더(기존 `Show(snap)`라 끊기면 아무것도 안 떴음) + **⚠ 배너** —
      STEERING_DIR 미설정 / snapshot 없음 / published_at stale>30s 시 표시(원인 표기, 비밀 미포함, naive-local 파싱). 커밋 `ea9a885`.
- [x] tsgo 0 errors (위 Step4 typecheck에 포함). (참고: MCP 미등록 감지는 사이드바에서 직접 불가 → 채널/snapshot 신선도로 데몬-다운 케이스 커버.)

## Step 7 — 테스트 · 마감 · 라이브 · 재핀
- [x] bun unit 26 launcher + 51 console-own green; bun build 클린. (파이썬 무회귀: 데몬 0 변경 — 별도 실행 불필요.)
- [x] **런처 코어 라이브 검증** — 실제 데몬 대상 read-only: preflight green, attach(advancing+busy 둘 다 start 0회), 토큰 present(미표시), 유닛 렌더 OK. (critic #1/#2/#3/#4 라이브 통과.)
- [x] **포크 UI 라이브 검증(사용자 머신)** — 로고(메인 OK; 종료화면 클립 발견→수정), 사이드바, 동작 확인됨. 남은 코딩용 copy(프롬프트/팁)는 **F7로 분리**(사용자 결정).
- [x] **서브모듈 재핀=A**: 포크 실브랜치 커밋 → `autostock-cli` 원격 push **성공**(SSH) → worktree에서 gitlink 재핀 커밋 `da724cf`. (폴백 불필요.)
- [x] aidlc-state.md/audit.md 갱신. (code-summary는 생략 — 상태/감사에 충분히 기록.)
- [ ] (남음) `feat/console-native-launcher` → **main 머지**(autostock를 main 체크아웃에서 실사용하려면 필요) — 외부 영향이라 사용자 승인 후.

## 리스크 / 정지점
- 포크 빌드/라이브(Step4–6 검증)는 사용자 머신 필요 → 해당 항목에서 정지·요청.
- 원격 push 인증 → Step7에서 정지·요청 가능.
