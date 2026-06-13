# F79 Application Design — Component Methods (signatures)

> 높은 수준의 시그니처. 상세 비즈니스 규칙은 Functional Design(per-unit)에서. TS 기준.
> ★ = 재사용(기존 함수). 신규는 주입형 의존성(fetcher/credentialsGet/sdk)로 테스트 가능하게.

## C1. ConnectionStore
- `pairFromQr(text: string): PairResult` ★ (`parsePairingPayload` 위임)
- `connect(server: ServerConnection.Http): void`
- `connectionState(): "online" | "reconnecting" | "offline"`  // NFR-7
- `scheduleReconnect(): void`  // 백오프

## C2. SnapshotController
- `assembleSnapshot(sdk, health, pendingCount): unknown`  // 부분/누락 허용
- `toDashboard(snapshot, {offline}): DashboardModel` ★
- `dashboardSummary(model): string` ★
- `refreshNow(): Promise<void>`  // FR-8 pull-to-refresh
- `isStale(model, nowMs, thresholdMs): boolean`  // NFR-7

## C3. SignedMutationGateway ★핵심
- `obtainAssertionHeader({fetcher, credentialsGet}): Promise<string>` ★
- `signedRespond(input: PermissionRespondInput): Promise<void>`
   // = obtainAssertionHeader → permission.respond({...input, headers:{"x-autostock-webauthn":sig}})
- `signedPrompt(input: SessionPromptInput): Promise<void>`  // FR-4, 동일 패턴
- 오류: `WebAuthnError` ★ → 호출자(C5/C8)가 한국어 표면화, **미전송(fail-closed)**

## C4. ApprovalQueueController
- `pending(): PermissionRequest[]`  // 기존 permission 컨텍스트 구독
- `badgeCount(): number`
- `nextForSheet(): PermissionRequest | null`  // FR-6 자동 팝업 순차
- `reject(id): void`  // 무서명

## C5. ConfirmSheet (뷰)
- props: `request, onApprove(): Promise<void>(→ C3.signedRespond), onReject(), error?`
- `open(request)` / `close()` (C4가 트리거)

## C6. DashboardView (뷰)
- props: `model: DashboardModel, onRefresh(), stale: boolean`
- 표시: equity/dayPnlPct/positionCount/symbols/healthOk/pendingApprovals/asOf/offline

## C7. DetailViews
- `PositionThesisView(symbol)` → steer_read thesis 조회 표시 (읽기전용)
- `HealthOverlay()` → 9차원 health 스냅샷 표시 (읽기전용)

## C8. SessionEntry (뷰)
- 기존 `session.tsx` 라우팅 ★재사용
- `sendInput(text)` → C3.signedPrompt (FR-4 게이트)

## C9. LockController
- `arm(timeoutMs=300_000)` / `touch()` (활동 시 리셋)
- `isLocked(): boolean`
- `unlock(): Promise<void>`  // 패스키/비번 재인증
- 잠금 시 C3 경로 fail-closed (클라이언트 한정 — 서버 연결 유지)

## C10. MobileShell (뷰)
- 라우팅: `/` (C6) · `/session/:id` (C8) · `/connect` (C1); 배지(C4)·잠금(C9) 오버레이

## S1. WebAuthnGate 확장 (서버)
- `isMutatingAutostockPermission(p): boolean` ★ (기존)
- `isRemoteOrigin(req): boolean` ★ (기존)
- `verifyAssertionHeader(header): Promise<Verdict>` ★ (기존)
- **신규**: `gateRemotePrompt(request): Promise<Response|null>`  // route()에 추가 —
  원격 session.prompt면 verifyAssertionHeader 강제, 무/무효 서명 → 401 deny(fail-closed)
