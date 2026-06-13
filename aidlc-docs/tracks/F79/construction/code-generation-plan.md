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
- [ ] C4 ApprovalQueueController (배지 + 자동 시트 트리거; permission.tsx 위)
- [ ] C5 ConfirmSheet 뷰 (승인→C3 서명 전송 / 거절 무서명)
- [ ] C9 LockController (비활성 타이머 → 클라 잠금 → 재인증)
- [ ] permission `respond`에 헤더 전달 경로 배선 (per-call headers)

## U3 — 셸·세션·다듬기
- [ ] C6 DashboardView (모바일 우선; equity/손익/포지션/건강/승인대기/asOf/offline/stale)
- [ ] C8 SessionEntry (기존 session.tsx 재사용 + 입력 C3 서명 prompt)
- [ ] C10 MobileShell 내비 + 배지 + 잠금 오버레이
- [ ] FR-8 pull-to-refresh 제스처

## 검증
- [x] app typecheck (tsgo -b) 클린 — 현 시점
- [x] addon 단위/PBT 테스트 그린 (30 pass)
- [ ] 데스크톱 가짜 패스키 e2e 시뮬 (흐름 A·B)
- [ ] 전체 console typecheck + 인접 회귀
- [ ] post-merge-guide (실기기 토폴로지 스모크 절차)

## 검증 메모
- PBT 발견: `toDashboard.positionCount`=전체 길이 vs `symbols`=유효심볼만 → 의도된 분기로 예시
  테스트 고정(snapshot.test.ts). 코드 변경 아님.
