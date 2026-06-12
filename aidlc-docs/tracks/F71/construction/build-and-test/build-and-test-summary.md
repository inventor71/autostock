# F71 — Build & Test Summary (기반 머지분)

> 스코프: **선택 A** — U1+U2+U3로직(기반)을 머지 직전까지. SolidJS 뷰 배선은 후속(F72, 실기기).

## 빌드
- TS/Bun. 신규 의존성: `qrcode-terminal`(launcher), `@simplewebauthn/server`(opencode fork).
- 빌드 단계 없음(인터프리티드). 정합성 = tsgo typecheck.

## 단위 테스트
| 스위트 | 결과 |
|--------|------|
| `operator-console/test/launcher-f71.test.ts` (U1) | **13 pass** — 비번 fail-closed / tailnet-전용 바인드 / QR 페이로드 / serveEnv wiring / systemd 유닛 렌더 |
| `packages/opencode/test/autostock-webauthn.test.ts` (U2) | **23 pass** — 뮤테이팅 분류(fail-closed) / loopback=in-process / 게이트 매트릭스(원격·서명·거부·긴급정지 무예외) / 챌린지 단일사용·TTL / basic-auth / https-only origin |
| `packages/app/src/addons/autostock/autostock.test.ts` (U3) | **15 pass** — QR 파싱 거부케이스 / WebAuthn ceremony 직렬화·취소·에러 / 대시보드 변환 매트릭스 |
| 인접 회귀 | launcher 스위트 144 pass, opencode webauthn+mcp 28 pass |

## 통합 / typecheck
- `bun run typecheck`(monorepo, tsgo) **19/19** — DOM WebAuthn 타입 + ServerConnection + Effect HTTP 정합.
- 서버 라우트 마운트는 코드 경로로 확인(server.ts에서 HttpApi 앞에 `/autostock/webauthn/*`).

## NFR 검증 매핑
| NFR | 상태 |
|-----|------|
| 1 보안(최우선) | ✅ 비번 fail-closed(U1) + 원격 뮤테이팅 서버측 WebAuthn 게이트(U2) + 긴급정지 무예외 + 이중 게이트(human-order-gate/RiskManager 불변) + 패스키 공개키만 |
| 2 프로덕션 무영향 | ✅ serve 미기동·loopback이면 데스크톱 TUI/데몬 경로 불변(게이트는 원격에만) |
| 3 가용성 | ✅ systemd 유닛(enable; 시작은 비번/tailscale 준비 후) |
| 4 사용성 | 부분 — 로직 완료, 화면(오프라인 배너 등)은 F72 |

## 알려진 한계 (이 머지분)
- **UI 없음**: U3는 클라이언트 로직까지. 실제 화면(대시보드/트레이스/QR스캔/confirm 시트/세션목록)은 **F72 후속**(실기기 검증과 함께).
- WebAuthn은 **https 필수** → `tailscale serve`(TLS, *.ts.net) + `AUTOSTOCK_WEBAUTHN_ORIGIN` 필요. 미설정 시 서명 검증 fail-closed(보안상 안전).
- 라이브 스모크(서버 실기동→폰 접속)는 뷰가 없어 현재 curl 수준만 가능 → post-merge-guide 참조.

## Build & Test 결론
기반 3유닛 그린(51 + 인접 회귀). **머지 가능 상태**. UI는 F72로 분리(사용자 결정).
