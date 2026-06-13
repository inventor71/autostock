# F79 Application Design — Components

> 클라이언트(`operator-console/cli/packages/app/src/addons/autostock/` + 뷰)와, FR-4 결정의
> 결과로 추가되는 서버 게이트 확장(`packages/opencode/src/server/autostock/`).
> 순수 로직(dashboard.ts/pairing.ts/webauthn-client.ts)은 **재사용**, 신규는 주로 뷰 + 어댑터 + 컨트롤러.

## 클라이언트 컴포넌트

### C1. ConnectionStore (페어링/연결)
- **책임**: QR/수동 입력을 `parsePairingPayload`(기존)로 `ServerConnection.Http`로 변환해 server
  컨텍스트에 저장. NFR-7 자동 재연결(백오프) + 연결상태(online/offline) 소스.
- **재사용**: `pairing.ts::parsePairingPayload`, `@/context/server`.

### C2. SnapshotController (대시보드 데이터)
- **책임**: 여러 읽기 소스(account/positions = SDK read, health = steer_read health verb,
  pending = C4 큐)를 **클라이언트에서 단일 snapshot 객체로 조립**해 `toDashboard()`(기존)에 투입.
  주기 폴링(NFR-2) + pull-to-refresh(FR-8) + `asOf` 기반 stale 판정(NFR-7).
- **재사용**: `dashboard.ts::toDashboard/dashboardSummary`.
- **설계 결정**: 서버에 신규 통합 snapshot 엔드포인트를 만들지 않고 **클라이언트 조립 어댑터**로 둔다
  (서버 표면 최소화; `toDashboard`는 이미 부분 데이터/누락에 never-throw).

### C3. SignedMutationGateway (서명 첨부 단일 관문) ★
- **책임**: 모든 **원격 mutating** 호출에 `x-autostock-webauthn` 헤더를 붙이는 **단일 chokepoint**.
  - permission 승인: `serverSDK.client.permission.respond({..., headers:{ "x-autostock-webauthn": sig }})`
  - 세션 입력(FR-4): `serverSDK.client.session.prompt({..., headers:{...}})`
- **메커니즘(코드 확인됨)**: SDK(`@hey-api/openapi-ts`)는 per-call `headers` 옵션
  (`sdk/.../core/types.gen.ts:37`)과 request 인터셉터(`sdk/.../client.ts:54` 기존 사용)를 지원.
  → **per-call headers 방식 채택**(명시적·국소적; 인터셉터의 암묵 전역 첨부보다 안전).
- **재사용**: `webauthn-client.ts::obtainAssertionHeader/optionsToRequest/serializeAssertion`.
- **fail-closed(SECURITY-15)**: 서명 취소/오류 시 호출 미전송 + 한국어 사유.

### C4. ApprovalQueueController (승인 큐/배지)
- **책임**: 기존 permission ask 스트림(`@/context/permission` + `server-sync`)을 구독해 pending
  mutating 승인을 큐로 노출(FR-6 배지 개수) + ConfirmSheet 자동 팝업 트리거(여러 건 순차).
- **재사용**: `@/context/permission`(respond/respondOnce 흐름), `permission-auto-respond`(분류 참고).

### C5. ConfirmSheet (뷰, FR-3)
- **책임**: mutating 승인 요청을 모바일 시트로 표시(도구/요약). 승인 탭→C3 경유 서명·전송,
  거절→무서명 reject. 취소/오류 한국어 표면화. **읽기/거절은 서명 불필요**(F75 토폴로지 준수).

### C6. DashboardView (뷰, FR-2/FR-8)
- **책임**: `DashboardModel` 렌더(equity/당일손익%/포지션+심볼/건강/승인대기/asOf/offline),
  pull-to-refresh, stale 배지. 모바일 우선 레이아웃(기존 opencode 디자인 토큰).

### C7. DetailViews (뷰, FR-7)
- **PositionThesisView**: 포지션 탭→thesis(steer_read thesis; F53 동등). 읽기전용.
- **HealthOverlay**: 건강 글리프 탭→9차원 오버레이(steering/health.json 파생; F69 동등). 읽기전용.

### C8. SessionEntry (뷰, FR-4)
- **책임**: 기존 `pages/session.tsx` 대화형 뷰로 라우팅(풀 재사용). 폰 입력(프롬프트/스티어링)은
  C3 경유로 서명 첨부 → 서버 게이트(S1) 통과. 읽기(스크롤/이어보기)는 무서명.

### C9. LockController (NFR-6)
- **책임**: 비활성 타이머(기본 5분) → **클라이언트 잠금만**(서버 연결·이벤트 스트림 유지).
  재접근 시 패스키/비번 재인증 전까지 mutating 경로 fail-closed. 잠금 중 읽기 차단(셸 가림).

### C10. MobileShell (FR-5)
- **책임**: 홈(C6) ↔ 세션(C8) ↔ 연결설정(C1) 내비 + 승인 배지(C4) 표면 + 잠금 오버레이(C9).

## 서버 컴포넌트 (FR-4 결정의 결과 — 신규 ★)

### S1. WebAuthnGate 확장 — 원격 session.prompt
- **현재(F75)**: `webauthn.ts`가 permission-reply의 mutating 분류(`isMutatingAutostockPermission`)
  + 원격 판정(`isRemoteOrigin`)에만 서명 강제.
- **추가**: 원격(`isRemoteOrigin`) `session.prompt`(및 v2.session.prompt) 요청에 동일 서명 검증
  적용 — 폰 세션 입력을 게이트(클라이언트가 유일 방어선이 되지 않게, SECURITY-08/11).
  in-process/host-local loopback(임베디드/attach TUI)은 기존대로 trusted(무서명).
- **재사용**: `verifyAssertionHeader`, `isRemoteOrigin`, 챌린지 스토어(F75).
- **범위 주의**: 이는 requirements 초안의 "서버측 WebAuthn 변경 out-of-scope"를 FR-4 선택이
  **의도적으로 좁게 확장**한 부분 — 승인 게이트에서 사용자 확인 필요.
