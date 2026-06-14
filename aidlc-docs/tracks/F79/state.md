# Track F79 — 모바일 PWA 실화면 완성 (F71/F75 후속)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F79
- **Title**: 모바일 PWA 실화면(SolidJS 뷰) 완성 — 홈 대시보드 + WebAuthn confirm 시트 배선 + 세션 뷰 (F71/F75 후속)
- **Type**: feature
- **Status**: merged → main fbc1bae (2026-06-14)  <!-- code-review 5건 반영, rebase→verify→merge. 대시보드 실데이터·세션서명 후속. -->
- **Branch**: feat/F79
- **Worktree**: .claude/worktrees/F79
- **Submodule branch**: — (monorepo; operator-console/cli/packages/app + opencode 변경)
- **Base commit**: ff15bbd (worktree 생성 시점 main HEAD; F78 머지 후)
- **Start Date**: 2026-06-13T06:24:26Z

## Extension Configuration
| Extension | Enabled | Mode | Decided At |
|---|---|---|---|
| Security Baseline | Yes | Full (blocking) | Requirements Analysis |
| Property-Based Testing | Yes | Full (blocking) | Requirements Analysis |

> WebAuthn 서명·basic-auth·외부 응답 파싱이 걸려 Security Baseline 관련. 순수 변환
> (dashboard `toDashboard`/`dashboardSummary`, 서명 페이로드 인코딩)에 PBT 라운드트립/불변식 적용.

## Scope
F71/U3가 로직만 출고하고 SolidJS 뷰 배선을 "실기기 검증분"으로 분리해, 폰에서 보이는 실제
화면이 없는 상태. 본 트랙이 그 뷰를 완성한다.

기존 자산 (operator-console/cli/packages/app/src/addons/autostock/):
- `dashboard.ts` — `toDashboard()`/`dashboardSummary()` 순수 변환 + `DashboardModel`
- `webauthn-client.ts` — `obtainAssertionHeader()` (정의·테스트만, 호출부 0)
- `pairing.ts` — QR 페어링
서버측 (operator-console/cli/packages/opencode/src/server/autostock/) WebAuthn 게이트는 F75로 강화 완료.

목표 (요청 원문 기준):
1. **홈 대시보드 화면 렌더링** — equity / 당일손익% / 포지션수+심볼 / 건강 / 승인대기 / 오프라인.
2. **WebAuthn confirm 시트를 mutating 승인 흐름에 실제 배선** — 폰에서 `x-autostock-webauthn`
   서명 헤더를 붙여 F75 게이트 통과 경로 활성화 (현재 폰 mutating 전부 거부 상태 해소).
3. **steer_read 패널 래핑 + TUI 세션 이어보기(US-8) 뷰**.

확정 결정 (F71 승계): UI=PWA / 제어=기존 뮤테이팅 도구만(신규 주문 작성 제외) / 홈=대시보드 우선.
범위 밖: 계정 자동detect(경로 B) / 푸시 알림 / 신규 수동 주문 / opentui 전체 포팅 / 네이티브 앱.

연관: F71(모바일 기반), F75(WebAuthn 게이트 강화), [[worktree-live-verification]].

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.
> 비워두면 `/ai-dlc-merge`가 `git diff --name-only`로 자동 추론.

- **공유 파일 (주의)**: operator-console/cli/packages/app/* (SolidJS 뷰) — F71 기반분 위 추가형.
- **API/시그니처 변경**: 미정 (대부분 추가형 뷰 배선 예상).
- **알려진 동시 변경**: F73(viz-shell, 별 패키지 viz-shell/), F76/F77/F78 — 현재로선 비중첩 추정.

## Stage Progress
- [x] Workspace Detection — brownfield, RE 스킵(CodeKB 존재)
- [x] Requirements Analysis — Standard (FR-1~8, NFR-1~7; Security/PBT Full) ✅ 승인
- [x] User Stories — 스킵 (F71 US-1/2/5/8 재사용, 요구사항이 흡수)
- [~] Workflow Planning — 경량 인라인 (단일 후속 기능; 설계→코드→테스트 직진)
- [x] Application Design — 완료 (components/methods/services/dependency + 통합 공백 4건 해소)
- [ ] Units Generation — Application Design에서 U1~U3 제안 (확정 대기)
- [x] Construction (per-unit Code Generation) — 코어+보안+뷰+셸 완료(데이터/세션서명 후속)
  - [x] U1 데이터·연결: C2 SnapshotController ✅ (C1 페어링/C7 상세 ✅; 실데이터 폴링=후속)
  - [x] U2 보안 mutating: C3 SignedMutationGateway ✅ + S1 서버 게이트 ✅ + fast-check ✅ + C4 queue ✅ + C9 lock ✅ + respondSigned ✅
  - [x] U3 셸: C6 DashboardView ✅ (리치+테마) / C5 ConfirmSheet ✅ / C7 DetailViews ✅ / C10 MobileShell+`/autostock` ✅ / FR-8 ✅
  - [~] C8 세션 입력 클라 서명 + 대시보드 실데이터 = **후속**(사용자 결정; serve read 엔드포인트 부재→F83/후속)
- [x] Build & Test — 41 addon + 40 server green, app·opencode tsgo 클린, Storybook 라이트/다크 스냅샷
- [x] post-merge-guide — `/autostock` 셸·승인흐름 라이브·데이터 후속·실기기 스모크 절차

## Construction 완료 메모 (마무리 2026-06-14)
- **완료(검증됨)**: 코어 5종 + 라이브 FR-3(respondSigned) + S1 서버 게이트 + 뷰 3종(리치 대시보드·
  ConfirmSheet·DetailViews, **라이트/다크 Storybook 스냅샷 검증**) + **C10 MobileShell + `/autostock`
  라우트**(permission 이벤트→승인 시트→서명, 비활성 잠금). app·opencode tsgo 클린, 81 tests green.
  커밋: c5fa1ea, 2aeacce, 9c9cd8e, 뷰/폴리시 커밋, mobile-shell 커밋.
- **후속(사용자 결정 = 데이터는 fast-follow)**: ① 대시보드 실데이터 — serve 서버 autostock 스냅샷
  read 엔드포인트(F83 카탈로그 기반) + 배선. ② 세션 입력 클라 서명 + 세션뷰 모바일 통합(서버 S1은
  이미 fail-safe). ③ 실기기 토폴로지 스모크. → **F79는 보안 백본+승인 UX+셸로 머지 가능**, 모니터링
  데이터는 후속 트랙.
- **F84(차트)** 는 이 대시보드 데이터(①)에 의존 — F79 머지 후 데이터 엔드포인트 → F84 순.

## 설계 확정 (Application Design)
- D-AD-1: WebAuthn 헤더 = SDK per-call `headers` 옵션(단일 관문 C3 SignedMutationGateway).
- D-AD-2: 대시보드 스냅샷 = 클라이언트 조립(서버 신규 엔드포인트 없음).
- D-AD-3: 세션 입력 = 허용 + WebAuthn 게이트 → 서버 게이트를 원격 `session.prompt`로 확장(S1).
- D-AD-4: 자동잠금 = 클라이언트 한정(서버 연결 유지, 재접근 재인증).
