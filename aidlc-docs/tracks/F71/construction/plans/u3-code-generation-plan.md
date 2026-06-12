# F71 / U3 pwa-client — Code Generation Plan

> Functional EXECUTE(화면 플로우). worktree feat/F71, `packages/app`.

## 구현 (프레임워크-무관 클라이언트 로직 — 테스트 가능)
- [x] `src/addons/autostock/pairing.ts` — QR 페이로드 → ServerConnection.Http 파싱(US-1)
- [x] `src/addons/autostock/webauthn-client.ts` — assert-options→credentials.get→base64(JSON)
      헤더 ceremony(US-5; fetch/credentials 주입식). b64url 헬퍼(브라우저 dep 회피)
- [x] `src/addons/autostock/dashboard.ts` — steer_read 스냅샷 → DashboardModel 순수 변환(US-2)
- [x] `src/addons/autostock/autostock.test.ts` — 15 pass (페어링/ceremony/대시보드 매트릭스)
- [x] tsgo typecheck 19/19 (DOM WebAuthn 타입 + ServerConnection 정합)

## 뷰 배선 (SolidJS) — **실기기 검증 필요분, 별도 마무리**
> 블라인드(렌더 확인 불가) 대규모 SolidJS 라우트/페이지를 한 번에 박으면 리스크↑·검증 0.
> 위 로직이 뷰가 바인딩할 안정 표면이므로, 뷰는 실기기/플레이라이트로 보며 마감한다.
> (post-merge-guide의 실사용 체크리스트가 이 단계를 커버.)
- [ ] 홈 대시보드 패널 — `toDashboard` 바인딩 + steer_read 폴링 + 오프라인 배너 (US-2/US-7)
- [ ] 트레이스 뷰어 — steer_read 턴 목록/상세 (US-3)
- [ ] QR 스캔 페어링 — `BarcodeDetector`(+폴백) → `parsePairingPayload` → 서버 등록 (US-1)
- [ ] WebAuthn confirm 시트 — permission ask 수신 → `obtainAssertionHeader` →
      permission.reply에 `x-autostock-webauthn` 헤더 첨부 (US-5)
- [ ] 세션 목록/이어가기 — `session.list` SDK 바인딩 (US-8)
- [ ] 홈 라우트를 대시보드 우선으로 (UAQ)

## 결정
- **D-U3-1**: 클라이언트 핵심 로직을 프레임워크-무관 모듈로 분리 → 단위테스트 가능 +
  뷰는 얇게. autostock 전용은 `addons/autostock/`에 격리(upstream rebase 표면 최소).
- **D-U3-2**: 뷰 배선은 실기기 검증과 묶어 마감(Build&Test의 라이브 스모크) — fake로
  증명 불가한 카메라/WebAuthn/SDK 스트림을 한 번에 실폰에서 확인.
