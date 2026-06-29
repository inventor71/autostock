# F93 — Requirements (모바일 실행 경로 배선 fix)

**Depth**: Standard. **Type**: bug-fix wiring (brownfield, monorepo).
**근거**: `aidlc-docs/mobile-realdevice-test-guide.md` §9 (직전 bring-up 실측).

## 1. 의도 (Intent)
모바일 PWA 스택(F71/F79/F86)이 단위테스트는 통과했으나, 실제 네트워크 리스너를 통과하는
실행 경로가 배선되지 않아 폰에서 동작하지 않는다. 와이어 너머로 동작하도록 최소·정확하게 수정하고,
"리스너를 통과하는" 검증을 추가해 회귀를 막는다.

## 2. 범위 (사용자 확정: R1+R2+R3 코드, R4 문서)

### FR-1 [R1, BLOCKER] autostock 라우트를 실제 리스너에 마운트
- `webauthn.route()`(register/assert/…)와 `dashboard-read.route()`가 `Server.listen()`이 서빙하는
  경로(`createRoutes` 기반)에서 `uiRoute`(`*` 캐치올)보다 **먼저** 평가되어야 한다.
- 두 route()가 모두 `null`(미매칭)이면 기존대로 `uiRoute`(SPA/업스트림 프록시)로 **fallback**.
- 결과: 와이어 너머 `GET /autostock/dashboard` → JSON(실데이터), `POST /autostock/webauthn/*`
  → JSON challenge. `GET /autostock`(셸 페이지) 및 기타 경로 → 기존대로 SPA fallback.
- 기존 `Server.Default().app.fetch`(in-process/test 경로)와 **동일 의미**를 리스너에서도 보장.
  중복 로직은 단일 소스로 공유(두 경로가 갈라지지 않도록).

### FR-2 [R2, MEDIUM] serve가 `.env`의 `AUTOSTOCK_WEBAUTHN_ORIGIN` 전달
- `autostock serve`(launcher `serveEnv`)가 `OPENCODE_SERVER_PASSWORD`와 동형으로 루트 `.env`에서
  `AUTOSTOCK_WEBAUTHN_ORIGIN`을 읽어 serve 프로세스 env에 주입한다(process.env가 우선, 없으면 .env).
- systemd 유닛 경로에서도 동일 보장(유닛이 launcher `serve` 서브커맨드를 실행하므로 자동 상속되는지
  확인; 별도 `EnvironmentFile`이 필요하면 문서화).
- 미설정 시 기존 fail-closed 동작 유지(보안 후퇴 금지).

### FR-3 [R3, MEDIUM] QR/pairing이 https origin을 굽도록
- `autostock qr` 페이로드의 서버 url이 https origin을 우선 사용한다. `AUTOSTOCK_WEBAUTHN_ORIGIN`
  (= 폰이 접근하는 https origin)이 설정돼 있으면 그것을 server url로 사용; 없으면 기존
  `http://<ts-ip>:4096`로 폴백하되 **경고 문구**로 https 필요성을 고지.
- pairing.ts 파싱은 https url을 그대로 수용(현재도 url 문자열 수용 — 회귀 없게 확인).

### FR-4 [R4, 문서] 단일 origin 미사용 — 검증된 두 origin runbook 문서화
- 코드 변경 없음. `mobile-realdevice-test-guide.md`를 갱신: bring-up에서 검증된 토폴로지
  (앱: vite/정적 :3000 → tailscale serve https 443 / API: `autostock serve --cors <origin>` :4096
  → tailscale serve https 8443), 폰 서버 등록(https), 패스키 등록·승인·잠금·대시보드 실데이터 절차.
- FR-1~3 반영 후 §9 블로커 해제 표기 + §2~§4 실행 절차를 "검증됨"으로 업데이트.

## 3. 비기능 요구 (NFR)
- **무회귀**: 데스크톱 TUI(loopback)·데몬 자동 턴·기존 타입드 라우트(/doc 등)·SPA 서빙 동작 불변.
- **fail-closed 보존**: webauthn 원격 게이트, basic-auth 401, 무서명 거부는 그대로.
- **추가형**: 외부 계약(경로/메서드/인증) 변화 없음 — 죽어있던 경로를 살리는 것.
- **테스트**: 리스너를 통과하는(실제 HTTP fetch) 회귀 테스트로 FR-1 증명.

## 4. 수용 기준 (Acceptance)
1. `Server.listen()`로 띄운 서버에 `GET /autostock/dashboard`(basic-auth) → 200 `application/json`,
   `published_at` 존재. 무인증 → 401. `POST` → 405(인증 후).
2. 동일 서버에 `POST /autostock/webauthn/register-options`(basic-auth) → 200 JSON challenge(HTML 아님).
3. `GET /autostock`(셸) 및 임의 비-API 경로 → 기존 SPA fallback(HTML) 유지. `/doc` → 200 유지.
4. `AUTOSTOCK_WEBAUTHN_ORIGIN`만 `.env`에 두고(환경 export 없이) `autostock serve` → webauthn 검증이
   origin을 인식(fail-closed 아님).
5. `AUTOSTOCK_WEBAUTHN_ORIGIN` 설정 시 `autostock qr` server url이 https origin.
6. 위를 리스너 통과 자동 테스트로 커버(직접 route() 호출 아님). 기존 단위테스트(webauthn 41/
   dashboard 15/addon 52/launcher-f71 13) 그린 유지.

## 5. 범위 밖 (Out of scope)
- R4 단일 origin 코드(임베드 빌드 / serve 정적 서빙) — 후속 트랙 후보.
- 폰→에이전트 프롬프트 전송 클라 서명(F79 알려진 한계), F84 차트, day P&L%/buying_power.

## 6. Extension Compliance 계획
### Security Baseline = **Enabled (Full, blocking)**
적용(applicable) 룰 — 본 트랙이 인증/원격 노출/라우팅을 직접 건드림:
- **SECURITY-08 (App-level access control)**: 살아난 라우트가 basic-auth/webauthn 게이트를 그대로
  통과시키는지 검증. CORS는 와일드카드 금지(`--cors`로 명시 origin만; 이미 동작 확인).
- **SECURITY-04 (HTTP security headers)**: HTML 서빙 경로(uiRoute)는 기존 CSP 유지 — fix가 헤더를
  약화시키지 않는지 확인.
- **SECURITY-15 (fail-safe/예외)**: route() 마운트가 예외 시 fail-closed·SPA fallback 안전 유지,
  500로 셸 깨지지 않음.
- **SECURITY-03 (로깅)**: 비번/서명/origin 등 비밀 미로깅(QR 경고 포함).
- **SECURITY-10 (공급망)**: 신규 런타임 의존성 도입 시 lockfile 핀(현재 신규 의존성 없을 전망).
- N/A: SECURITY-01/02/06/07/09(인프라/IAM/네트워크 프로비저닝 무관), 12/13/14(신규 인증·CI·알림
  도입 아님; 기존 webauthn 보존만), 05(신규 입력 파라미터 없음 — 경로는 고정 파일명), 11(신규 설계 아님).

### Property-Based Testing = **Partial** (PBT-02/03/07/08/09만 강제)
- 대상: 순수 함수 한정 — FR-3의 pairing 페이로드 인코딩/파싱(round-trip, PBT-02), origin/url 정규화
  불변식(PBT-03). 프레임워크: **fast-check**(이미 F79가 devDep로 도입, PBT-09 충족).
- 라우팅 마운트(FR-1)·env 주입(FR-2)은 통합/example 테스트(+ 리스너 통과 회귀)로 — PBT 비대상(N/A).
</content>
