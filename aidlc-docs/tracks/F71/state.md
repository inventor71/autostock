# Track F71 — autostock 모바일(안드로이드) 앱 — 경로 A (Tailscale + opencode serve + PWA)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F71
- **Title**: 폰에서 autostock operator 콘솔 — Tailscale + `opencode serve` + PWA(packages/app)
- **Type**: feature
- **Status**: merged → main fdfc041 (2026-06-12)
- **Branch**: feat/F71
- **Worktree**: .claude/worktrees/F71
- **Submodule branch**: — (monorepo; operator-console/* 변경 포함)
- **Base commit**: 76ff7b6
- **Start Date**: 2026-06-10

## Extension Configuration
- **Security Baseline**: **Enabled (Applicable)** — 트레이딩 제어 네트워크 노출 + 폰 뮤테이팅.
  강제: OPENCODE_SERVER_PASSWORD 필수(fail-closed), `:4096` tailnet 한정, **긴급정지 포함 모든
  뮤테이팅 WebAuthn 서명 + 서버측 검증**(클라이언트 게이트 아님), human-order-gate/RiskManager
  이중 게이트 유지, 패스키는 공개키만 저장, QR(URL+비번)은 요청 시 표시·로그 미기록.
- **Property-Based Testing**: **Partial** — 순수 로직(뮤테이팅 분류/서명 검증 판정)에 한정,
  UI/통합 비대상. (U2 NFR에서 최종 확정)

## Scope (Q&A + UAQ 확정)
경로 A MVP: PC(데몬 호스트)에서 `opencode serve`(TUI와 동일 MCP/STEERING wiring, systemd 상시)
→ 폰이 **Tailscale**로 도달 → **PWA(packages/app)**. 모바일 = 대화형 operator + 패널.

확정 결정: UI=PWA / 제어=기존 뮤테이팅 도구만(신규 주문 작성 제외) / confirm=WebAuthn 패스키
(**긴급정지 포함 예외 없음**) / 네트워크=Tailscale / 인증=서버비번+ACL / 등록=QR(URL+비번) 1회 /
serve=systemd / 데이터=steer_read 패널 래핑 / **홈=대시보드 우선** / **US-8 TUI 세션 이어보기 채택**
(feasibility ✅: 글로벌 SQLite+WAL+session.list).

범위 밖: 계정 자동detect(경로 B), 푸시 알림, 신규 수동 주문, opentui 대시보드 전체 포팅, 네이티브 앱.

문서: `inception/requirements/requirements.md`(FR-1~10) · `inception/user-stories/user-stories.md`
(P1, US-1~8) · `inception/plans/workflow-plan.md`(3유닛) · `inception/application-design/
application-design.md`(C1~C11, D1~D5, R1~R4) · 조사 `aidlc-docs/research/mobile-app-investigation.md`.

## Merge Risk Notes
> merge-awaiting 전환 시 보강.

- **공유 파일 (주의)**: `operator-console/launcher/*`(cli/config/unit-template/install),
  opencode fork `packages/opencode/src/server/*`(라우트 추가), `packages/app/*`(PWA addon).
- **API/시그니처 변경**: 없음(추가형). permission.reply/session.permissionRespond 핸들러에 게이트 한 블록 추가(로직 보존, 원격에만 동작). server.ts fetch에 라우트 1개 prepend.
- **알려진 동시 변경**: 현재 operator-console를 만지는 활성 트랙 없음(F33 paused).

## Stage Progress
- [x] Workspace Detection — brownfield, codekb
- [x] Requirements Analysis — standard ✅ 승인 (FR-1~10)
- [x] User Stories — EXECUTE ✅ 승인 (P1, US-1~8 + AC)
- [x] Workflow Planning ✅ 승인 (U1 server-runtime / U2 security-gate / U3 pwa-client 순차)
- [x] Application Design ✅ 승인 (US-8 feasibility ✅ 채택, C1~C11, D1~D5)
- [x] Units Generation — Workflow Plan에 통합(3유닛 확정)
- [ ] Construction (per-unit)
  - [x] U1 server-runtime — serve/qr 서브커맨드 + systemd 유닛 + QR (테스트 13, launcher 스위트 144 pass)
  - [x] U2 security-gate — WebAuthn 라우트+양쪽 reply 게이트(원격 한정)+fail-closed 분류 (23 pass, tsgo 19/19)
  - [~] U3 pwa-client — 클라이언트 로직(페어링/WebAuthn confirm/대시보드 변환) +테스트 15 pass; SolidJS 뷰 배선은 실기기 검증분으로 분리
- [x] Build & Test — 51 pass(U1 13/U2 23/U3로직 15) + 인접 회귀, tsgo 19/19, post-merge-guide 작성
