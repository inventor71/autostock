# Track F93 — 모바일 실행 경로 배선 fix (리스너 라우트 마운트 + env/QR origin + 단일 origin runbook)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F93
- **Title**: 모바일 실행 경로 배선 fix — autostock API 라우트를 실제 리스너에 마운트(R1 블로커) + serve가 .env WEBAUTHN_ORIGIN 전달(R2) + QR https origin(R3) + 단일 origin 배포 runbook(R4)
- **Type**: feature (bug-fix wiring)
- **Status**: merge-awaiting  <!-- Build & Test green 2026-06-28; /ai-dlc-merge → merged -->
- **Verify ledger**: typecheck(opencode) 0err / 리스너 회귀 6 / 런처 24 / 기존 autostock 56 / 앱 애드온 52 / 실데이터 라이브 스모크 OK (dashboard JSON 실값 + webauthn challenge). httpapi-listen 로그 테스트 flaky = base에서도 실패(F93 무관).
- **Branch**: feat/F93
- **Worktree**: .claude/worktrees/F93
- **Submodule branch**: — (monorepo; operator-console/cli 변경)
- **Base commit**: 42d0398 (main HEAD at branch creation)
- **Start Date**: 2026-06-28T08:35:16Z

## Extension Configuration
- **Security Baseline**: **Enabled (Full, blocking)** — 적용: SECURITY-08(접근제어/CORS), -04(HTML 헤더 보존),
  -15(fail-closed/SPA fallback), -03(비밀 미로깅), -10(공급망/lockfile). N/A: -01/02/05/06/07/09/11/12/13/14
  (인프라/IAM/신규 입력·인증·CI·알림 무관 — requirements.md §6 근거).
- **Property-Based Testing**: **Partial** (PBT-02/03/07/08/09 강제) — 순수 함수만(pairing 페이로드
  round-trip, origin/url 불변식). 프레임워크: fast-check(F79 도입분 재사용). 라우팅/env는 통합·리스너
  통과 테스트(PBT N/A).

## Scope
직전 bring-up(guide §9) 실측으로 드러난 모바일 런타임 배선 갭을 한 트랙으로 수정한다.

- **R1 [BLOCKER]**: `webauthn.route()` + `dashboard-read.route()`가 `Server.Default().app.fetch`
  (`opencode/src/server/server.ts:63-68`)에만 마운트됨 → 실제 리스너 `Server.listen()` →
  `HttpRouter.serve(createRoutes())`(`server.ts:111`)는 이를 건너뛰어 `/autostock/*`가 `uiRoute`
  캐치올로 떨어져 SPA HTML 반환. → autostock route()를 리스너 경로에 `uiRoute`보다 **앞**에 마운트
  (SPA fallback 공존). **리스너를 통과하는 회귀 테스트** 추가(직접 route() 호출 아님).
- **R2 [MEDIUM]**: `serveEnv`가 `.env`의 `AUTOSTOCK_WEBAUTHN_ORIGIN`을 읽어 serve 프로세스에 주입
  (현재 비번만 직접 읽음 → origin 미전달 시 webauthn fail-closed). systemd 유닛 정합 포함 검토.
- **R3 [MEDIUM]**: `autostock qr` / pairing 페이로드가 https origin을 굽도록(현재 `http://<ip>:4096`).
- **R4 [설계]**: 폰이 우리 `/autostock` 앱을 받는 단일 origin 배포 경로 확정 + runbook
  (임베드 빌드로 serve 단일포트 vs `packages/app` 정적 서빙). 코드 범위는 Requirements에서 확정.

근거/실측: `aidlc-docs/mobile-realdevice-test-guide.md` §9. 연관: F71(serve/webauthn), F86(dashboard
endpoint), F79(모바일 셸), F84(모바일 차트 — 본 fix 위에 의존). [[worktree-live-verification]]

## Merge Risk Notes
- **Base 추적**: 브랜치 base=42d0398. 작업 중 병렬 **F92(브로커 provider 정합성)가 main에 머지**됨
  (main now 36afc5e). F92는 Python(main.py/src/agent·execution·monitoring/tests)+자체 docs+aidlc-state.md만
  변경 → **F93 코드 파일과 겹침 0**(확인) → **클린 rebase 예상**.
- **실제 변경 파일(4)**: `…/server/routes/instance/httpapi/server.ts`(autostockRoute 마운트),
  `launcher/serve.ts`(env/QR origin), `test/launcher-f71.test.ts`(+11), `…/test/server/autostock-listener.test.ts`(신규).
  (계획상 `server/server.ts`로 봤으나 실제 수정은 `routes/.../httpapi/server.ts` createRoutes였음.)
- **API/시그니처 변경**: 없음(내부 라우트 마운트 위치). 외부 계약은 오히려 복구(죽어있던 /autostock/* 살아남).
- **registry**: F93 행은 이미 main에 커밋됨(F92 close 커밋에 함께 스윕). 브랜치는 aidlc-state.md 미수정 → 충돌 없음.
- **알려진 동시 변경**: F84(모바일 차트, `packages/app`) — 디렉터리 다름, 본 fix 위에 의존.

## Stage Progress
- [x] Workspace Detection — brownfield, RE 스킵(CodeKB)
- [x] Requirements Analysis — Standard + extension opt-in (Security Full / PBT Partial). 승인됨.
- [x] User Stories — SKIP (내부 배선 fix, 신규 사용자 워크플로 없음)
- [x] Workflow Planning — 경량 인라인
- [x] Application Design — 경량(라우트 마운트 방식 = Effect HttpRouter 특정성 우선, toWeb/fromWeb 브리지)
- [x] Units Generation — SKIP (단일 유닛)
- [x] Construction (Code Generation) — FR-1(server.ts autostockRoute) + FR-2/FR-3(serve.ts) + 테스트
- [x] Build & Test — typecheck/리스너 회귀/런처/기존/애드온 전부 green + 실데이터 라이브 스모크. post-merge-guide 작성.
