# F93 — Build & Test Summary

작은 배선 fix라 build/unit/integration 지침을 본 요약에 통합한다(별도 파일 분리 생략).

## 변경 파일 (4)
| 파일 | 변경 | FR |
|---|---|---|
| `operator-console/cli/packages/opencode/src/server/routes/instance/httpapi/server.ts` | `autostockRoute` 레이어 추가(webauthn+dashboard route()를 toWeb/fromWeb로 브리지, uiRoute 앞 mergeAll) + `HttpServerRequest` import | FR-1 |
| `operator-console/launcher/serve.ts` | `WEBAUTHN_ORIGIN_KEY`/`resolveWebauthnOrigin` 추가, `serveEnv` origin 주입, `resolveServeContext` origin 노출, `runQr` https 페어링+경고 | FR-2, FR-3 |
| `operator-console/test/launcher-f71.test.ts` | FR-2/FR-3 example 테스트 + PBT-02 round-trip(fast-check) (+11) | test |
| `operator-console/cli/packages/opencode/test/server/autostock-listener.test.ts` | **신규** — `Server.listen()` 통과 회귀 테스트(6) | FR-1 test |

## Build
- 코드 변경은 opencode(TS) + launcher(TS). 빌드 산출물 없음(소스 실행). 타입 게이트로 빌드 검증:
  - `cd operator-console/cli/packages/opencode && bun run typecheck` → **exit 0, 에러 0** ✅
    (FR-1의 `HttpServerRequest.toWeb`/`HttpServerResponse.fromWeb` 타입 정합 확인)

## Unit / Integration 테스트 (실행 결과)
| 스위트 | 명령 | 결과 |
|---|---|---|
| **리스너 통과 회귀(FR-1)** | `opencode$ bun test test/server/autostock-listener.test.ts` | **6 pass** ✅ |
| 런처(FR-2/FR-3 + PBT-02) | `operator-console$ bun test test/launcher-f71.test.ts` | **24 pass** (기존 13 +11) ✅ |
| 기존 autostock 단위(회귀) | `opencode$ bun test test/autostock-webauthn.test.ts test/autostock-dashboard.test.ts` | **56 pass** ✅ |
| 앱 애드온(회귀) | `app$ bun test --preload ./happydom.ts src/addons/autostock` | **52 pass** ✅ |

## 라이브 스모크 (실데이터, worktree 코드)
worktree opencode를 `127.0.0.1:4097`(STEERING_DIR=실 steering, AUTOSTOCK_WEBAUTHN_ORIGIN 설정)로 기동:
- `GET /autostock/dashboard` (basic-auth) → **200 `application/json`** + 실데몬 데이터(equity 99939.58,
  cash 93802.62, 2 positions, fresh published_at). **main에선 동일 호출이 `text/html`(SPA)였음** → FR-1 입증.
- `POST /autostock/webauthn/register-options` → **200 JSON challenge**, `rp.id=vinn-mini.tail49dcde.ts.net`
  (AUTOSTOCK_WEBAUTHN_ORIGIN에서 rpID 파생) → FR-1 + FR-2 입증.

## 알려진 사항 (F93 무관)
- `opencode$ test/server/httpapi-listen.test.ts > "default in-process handler does not emit Effect HTTP
  response logs"` — **full-file 실행 시 flaky 실패**. **base(42d0398, F93 변경 없음)에서도 동일하게
  실패**(run #1/#2 재현), 격리 실행은 pass. 교차 테스트 stderr 캡처 오염으로, F93과 무관한 기존 결함.
  본 트랙 범위 밖(별도 처리 권장).

## Extension Compliance
- **Security Baseline (Full)**: SECURITY-08 ✅(살아난 라우트가 basic-auth+authOnlyRouterLayer 게이트
  유지, CORS 와일드카드 없음 — `--cors` 명시 origin), -04 ✅(uiRoute HTML CSP 경로 무변경), -15
  ✅(route null→404 fallback, dashboard never-throw, defect→errorLayer; serve origin 미설정 시 webauthn
  fail-closed 보존), -03 ✅(QR 경고는 키 이름만, 비번/origin 값 미로깅), -10 ✅(신규 런타임 의존성
  없음; fast-check/qrcode-terminal 모두 기존 lockfile 고정). 나머지 N/A(인프라/IAM/신규 입력·인증·CI).
- **PBT (Partial)**: PBT-02 ✅(pairing payload round-trip property, fast-check), PBT-07/08 ✅(fast-check
  기본 생성기/shrinking/seed), PBT-09 ✅(fast-check 기존 도입분). 라우팅(FR-1)/env IO(FR-2)는 순수
  변환 아님 → PBT N/A, 리스너 통과 통합 테스트로 커버.
</content>
