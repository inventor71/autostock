# F79 Construction — Code Generation Plan (checkboxes)

> 단일 후속 기능, 트랙 규모 작아 단일 코드젠 패스로 진행(자율). Application Design의 U1~U3를
> 작업 묶음으로 사용. 각 항목 완료 시 즉시 [x] (CLAUDE.md 플랜 체크박스 규칙).

## U1 — 데이터·연결 기반
- [x] C2 SnapshotController 순수 코어 (`snapshot.ts`: assembleSnapshot/buildDashboard/isStale)
- [x] C2 테스트 (PBT-03 불변식 + isStale fail-safe + 예시) — `snapshot.test.ts`
- [ ] C1 ConnectionStore (페어링 진입 + 재연결/offline) — 뷰 배선
- [ ] C7 DetailViews 읽기 경로 (thesis / health 9차원) — steer_read 조회
- [ ] SnapshotService 폴링 + pull-to-refresh(FR-8) 배선

## U2 — 보안 mutating 경로 (핵심)
- [x] C3 SignedMutationGateway (`signed-mutation.ts`: withWebAuthn, WEBAUTHN_HEADER, LockedError)
- [x] C3 테스트 (서명통과/취소/4xx/잠금 fail-closed) — `signed-mutation.test.ts`
- [x] fast-check 직접 devDependency 추가 (PBT-09)
- [x] S1 서버 게이트 확장 — 원격 `session.prompt` 서명 강제 (webauthn.ts `checkPrompt`/`promptNeedsAssertion` + session.ts `gateRemotePrompt` 배선: prompt + promptAsync)
- [x] S1 서버 테스트 (autostock-webauthn.test.ts +7: 원격 prompt 무서명 거부 / loopback·in-process trusted / tailscale hop 거부) — 40 pass
- [x] C4 ApprovalQueueController 코어 (`approval-queue.ts`: selectPending/badgeCount/nextForSheet) + 테스트(PBT 포함)
- [x] C5 ConfirmSheet 뷰 (`confirm-sheet.tsx`: 승인→C3 서명 / 거절 무서명 / busy·error UX) — tsgo 클린
- [x] C9 LockController 코어 (`lock.ts`: shouldLock/msUntilLock) + 테스트(PBT)
- [x] permission `respondSigned` 라이브 배선 — withWebAuthn → serverFetcher(인증) → SDK per-call headers → 서버 게이트. app tsgo 클린(=SDK 헤더 수용 검증). `webauthn-fetch.ts` 헬퍼(순수부 테스트).

## U3 — 셸·세션·다듬기
- [x] C6 DashboardView (`dashboard-view.tsx`: equity/손익/포지션칩/건강글리프/승인배지/asOf/offline/stale/새로고침) — tsgo 클린
- [x] C7 DetailViews (`detail-views.tsx`: PositionThesisView + HealthOverlay, 읽기전용) — tsgo 클린
- [x] C10 MobileShell (`mobile-shell.tsx`) + `/autostock` 라우트(app.tsx lazy) — permission.asked/.replied 이벤트 구독→승인큐→ConfirmSheet→respondSigned(승인)/respond(거절), 배지, 비활성 잠금 커튼(패스키 해제), 세션 링크. app tsgo 클린(=실 컨텍스트/SDK 이벤트 타입 정합).
- [x] FR-8 pull-to-refresh — 셸에서 onRefresh→touch 배선(대시보드 새로고침). (제스처 폴리시는 후속)
- [~] **C8 세션 입력 클라 서명 — 후속(데이터 채널과 함께)**: 서버 게이트 S1이 원격 무서명 prompt를
  거부(fail-safe)하므로 보안은 닫힘. 폰에서 *보내* 통과시키는 클라 서명은 세션뷰 모바일 통합 +
  데이터 채널과 함께. (사용자 결정: 데이터는 후속)
- [~] **대시보드 실데이터 — 후속**: serve 서버에 autostock 스냅샷 read 엔드포인트 부재(F83이 mobile을
  deferred). 셸은 빈 모델 graceful 렌더 + "데이터 연결 후속" 고지. 승인·잠금·세션링크는 동작.

## 검증
- [x] app typecheck (tsgo -b) 클린 — 현 시점
- [x] addon 단위/PBT 테스트 그린 (30 pass)
- [ ] 데스크톱 가짜 패스키 e2e 시뮬 (흐름 A·B)
- [ ] 전체 console typecheck + 인접 회귀
- [ ] post-merge-guide (실기기 토폴로지 스모크 절차)

## 검증 메모
- PBT 발견: `toDashboard.positionCount`=전체 길이 vs `symbols`=유효심볼만 → 의도된 분기로 예시
  테스트 고정(snapshot.test.ts). 코드 변경 아님.
