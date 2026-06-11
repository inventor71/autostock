# F71 / U2 security-gate — Code Generation Plan (완료 기록)

> Functional+NFR(보안 핵심)은 application-design C4~C6 + 본 구현 주석으로 통합 기술.

## 구현
- [x] `packages/opencode/src/server/autostock/webauthn.ts` (fork-격리 신규)
      — 뮤테이팅 분류(fail-closed), loopback 판정(undefined=in-process=로컬),
      decideGate 순수 코어, 패스키 store(공개키만), 단일사용 챌린지(TTL),
      basic-auth, register/assert-options/register 라우트, checkReply
- [x] `server.ts` — /autostock/webauthn/* 마운트(HttpApi 앞)
- [x] `handlers/permission.ts` + `handlers/session.ts(permissionRespond)` — 원격
      뮤테이팅 승인 게이트(두 reply 경로 모두)
- [x] deps: `@simplewebauthn/server`
- [x] tests: `test/autostock-webauthn.test.ts` 23 pass (분류/루프백/게이트 매트릭스/
      챌린지 단일사용·만료/인증/https-only origin)
- [x] typecheck: tsgo 19/19

## 핵심 결정 (구현 중 확정)
- **D-U2-1 (TUI 보호)**: TUI도 SDK(HTTP)로 reply → 무차별 게이트는 데스크톱 파괴.
  → **원격(비-loopback)에만** 서명 요구. in-process(remoteAddress=none)=로컬 취급
  (폰은 항상 소켓 경유라 우회 불가).
- **D-U2-2 (steer 포함)**: steer verb 구분 없이 autostock_steer ask 전체 서명
  (UAQ "모든 뮤테이팅 동일 서명"과 합치; metadata가 비어 verb 식별 불가이기도 함).
  → US-4 AC3(비뮤테이팅 steering 무서명)는 **원격에 한해 강화로 대체** — 문서화.
- **D-U2-3 (secure context)**: WebAuthn은 https 필수 → `AUTOSTOCK_WEBAUTHN_ORIGIN`
  (tailscale serve의 *.ts.net https origin) env 주입, 미설정 시 검증 fail-closed.
  배포 전제에 `tailscale serve` 추가 (post-merge-guide에 기재 예정).
- **프로파일**: opencode.json의 뮤테이팅=ask 기존 체계 + serve의 non-supervisor env(U1)로 충족 — 추가 변경 불요.
