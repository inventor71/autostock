# 모바일 PWA 실기기 테스트 가이드 (F71 + F79 + F86 통합)

> 대상: 폰(안드로이드/아이폰)에서 autostock operator 콘솔(PWA)을 실제로 띄워 **대시보드 실데이터
> 조회 + 패스키 승인 + 잠금**까지 end-to-end 검증. 코드 변경 없음 — 머지된 main(F71/F79/F86)을
> 그대로 사용. F84(차트)는 아직 미머지라 이 가이드 범위 밖.
>
> 작성 2026-06-28. 근거: 호스트 측 테스트/동작은 작성 시점에 실제 실행해 그린 확인(§7). 실기기
> end-to-end는 F71/F79/F86 모두 "미검증 부채"로 남아 있어, 본 가이드가 그 1회 패스 절차다.

---

## 0. 현재 호스트 상태 (작성 시점 점검 결과)

**이미 그린(내가 실행함, §7 증거):**
- opencode 서버 테스트: webauthn 41 pass / dashboard 15 pass
- PWA 애드온 테스트: autostock addon 52 pass (5 files)
- 런처 테스트: launcher-f71 (serve/qr fail-closed) 13 pass
- 라이브 fail-closed: `autostock qr` → 비번 미설정이라 거부됨(정상)

**아직 미충족(실기기 전 반드시 셋업해야 함 — §2):**
- ❌ `tailscale` 미설치 / 미기동
- ❌ 루트 `.env`에 `OPENCODE_SERVER_PASSWORD` 없음
- ❌ 루트 `.env`에 `AUTOSTOCK_WEBAUTHN_ORIGIN` 없음

→ 즉 코드는 준비됐고, **네트워크/비밀값 셋업 3건 + 폰 1대**만 갖추면 바로 테스트 가능.

---

## 1. 아키텍처 한 장 요약 (무엇을 검증하는가)

```
[데몬(python)] --발행--> steering/{snapshot,health,monitor,pending_approvals}.json
       |                                  ^
       | (in-process 에이전트 프롬프트, 게이트 안 됨)
       v                                  | (파일 read만, 브로커 호출 X)
[opencode serve : 4096]  --- autostock 라우트 ---
   - tailnet 인터페이스 IP에만 바인드 (0.0.0.0 폴백 없음)
   - basic-auth (OPENCODE_SERVER_PASSWORD)
   - GET /autostock/dashboard      (read; basic-auth만)        ← F86
   - POST /autostock/webauthn/*    (패스키 등록/검증)          ← F71
   - 원격 session.prompt / 뮤테이팅 = WebAuthn 서명 요구        ← F79 S1
       ^
       | tailscale (같은 tailnet) + (HTTPS는 tailscale serve로 TLS 프론트)
       |
[폰 PWA: packages/app, Vite SolidJS]  route /autostock → mobile-shell.tsx
   - 서버연결 = QR(서버 url + 비번)로 페어링, fetch는 그 url을 베이스로 사용
   - DashboardView(실데이터 5s 폴) + ConfirmSheet(패스키 승인) + 잠금 커튼
```

핵심 보안 모델: **읽기 = basic-auth, 뮤테이팅(취소/청산/긴급정지/steer/prompt) = WebAuthn 패스키
서명 + 서버측 검증**(클라 게이트 아님). 호스트-로컬(데몬/데스크톱 TUI loopback)은 무게이트 — 평소대로.

---

## 2. 전제조건 셋업 (실기기 전, 1회)

### 2-1. Tailscale (PC + 폰 같은 tailnet)
```bash
# PC
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4          # 예: 100.x.y.z  ← serve가 이 인터페이스에만 바인드
```
폰에도 Tailscale 앱 설치 후 같은 계정으로 로그인. (ACL로 접근 기기 제한 권장.)

### 2-2. 서버 비번 (fail-closed의 근거)
루트 `.env`에 추가:
```
OPENCODE_SERVER_PASSWORD=<길고-강한-랜덤-비번>
```
없으면 `autostock serve`/`qr`가 기동 거부(§0에서 라이브 확인됨).

### 2-3. HTTPS origin (WebAuthn 필수) — ⚠️ 여기가 핵심
패스키 API는 **secure context(https)** 에서만 동작한다. 서버는 패스키 검증 시
`AUTOSTOCK_WEBAUTHN_ORIGIN`(과 그 hostname을 rpID로) 사용하며, 이 값은 **폰에서 PWA 페이지가
로드되는 origin과 정확히 일치**해야 검증이 통과한다.

```bash
# :4096 을 *.ts.net 호스트네임에 TLS로 프록시
tailscale serve --bg --https=443 http://127.0.0.1:4096
tailscale serve status        # https://<pc>.<tailnet>.ts.net 확인
```
루트 `.env`에 추가:
```
AUTOSTOCK_WEBAUTHN_ORIGIN=https://<pc>.<tailnet>.ts.net
```

> **⚠️ 알려진 토폴로지 간극 (실기기에서 가장 먼저 확인할 것):**
> `autostock qr`가 굽는 페어링 페이로드의 서버 url은 **`http://<ts-ip>:4096`** 이다(raw http).
> 그런데 (a) 패스키는 https 페이지에서만 동작하고, (b) https로 로드된 PWA 페이지는 http API를
> fetch하면 **mixed-content로 브라우저가 차단**한다. 따라서 실제 end-to-end가 되려면 **PWA 페이지와
> :4096 API를 동일한 https `*.ts.net` origin으로 묶어** 접근해야 한다(위 `tailscale serve`가 그 역할).
> QR 스캔 대신 **폰에서 서버를 https origin으로 수동 등록**하거나, QR로 잡힌 url을 https로 바꿔야 할
> 수 있다. 이 한 지점이 그동안 미검증으로 남은 부채의 핵심 — **본 패스의 1순위 확인 항목**이며, 수동
> 워크어라운드로 안 풀리면 "QR이 https origin을 굽도록" 별도 fix 트랙으로 처리(코드 변경).

### 2-4. 데몬 + 콘솔/앱 빌드
```bash
# 데몬 가동 (steering/*.json 발행 — 없으면 대시보드는 빈-모델/오프라인 = graceful 정상)
autostock                      # 또는 평소 데몬 기동 방식

# 콘솔/앱 빌드 (서버 라우트 + PWA 반영)
cd operator-console/cli/packages/opencode && bun run build || true
cd ../app && bun run build
```

---

## 3. 기동 절차

```bash
# 1) 서버 기동 (둘 중 하나)
autostock serve                                   # 포그라운드, 로그 직접 확인
# 또는 systemd:
systemctl --user start autostock-serve            # install이 enable해 둠(자동시작은 안 함)
systemctl --user status autostock-serve

# 정상 로그: "autostock serve: http://<ts-ip>:4096 (tailnet 전용 바인드, 비번 필수)"

# 2) PWA를 https origin으로 노출 (2-3에서 tailscale serve 이미 켰다면 생략 가능)
#    페이지(packages/app)와 :4096 API가 같은 https *.ts.net origin으로 도달하도록 구성

# 3) 폰 페어링 QR
autostock qr                                      # 터미널에 QR + 서버 url 표시
# ⚠️ 비번 포함 → 스캔 직후 터미널 화면 클리어(clear). 로그로 남기지 말 것.
```

폰에서: ① Tailscale on → ② 브라우저로 `https://<pc>.<tailnet>.ts.net/autostock` 열기
→ ③ 서버 추가(QR 스캔 또는 url+비번 수동, **2-3 간극 주의**) → ④ 패스키 등록(지문/Face).

---

## 4. 실기기 테스트 체크리스트

### A. fail-closed (호스트 — 이미 검증됨, 재현 가능)
- [x] 비번 없이 `autostock serve`/`qr` → 거부 (§0/§7에서 확인)
- [ ] tailscale 미가동 시 → "tailscale IPv4 못 찾음"으로 거부(0.0.0.0 폴백 없음)

### B. 보안 게이트 (원격 vs 로컬)
- [ ] 데스크톱 TUI(attach/embedded)에서 에이전트 프롬프트/steer → **정상 동작**(게이트 안 됨)
- [ ] 데몬 자동 턴 → 정상
- [ ] tailscale 경유로 서명 헤더 없이 `POST /session/<id>/prompt` 호출(curl) → **400 거부**
      (서버 로그 `autostock: remote prompt gated`)
- [ ] 무인증 `curl .../autostock/dashboard` → **401**
- [ ] `curl -X POST .../autostock/dashboard` → **405**

### C. 셸 + 대시보드 실데이터 (핵심)
- [ ] 폰 PWA `/autostock` 접속 → 셸 표시(헤더/배지)
- [ ] 대시보드에 **실잔고·현금·종목별 P&L%·건강·승인대기수·시장세션·에이전트 최근활동** 표시
- [ ] **~5s마다 자동 갱신**, 상단 새로고침 탭 → 즉시 갱신
- [ ] 데몬 미발행/워밍업 시 → 빈-모델 + "오프라인/stale" 표시(셸 안 깨짐)

### D. 승인 시트 + 잠금 (패스키)
- [ ] 에이전트가 mutating autostock 도구 요청 → 셸에 **승인 시트 자동 표시**
- [ ] "승인 — 지문 서명" → 패스키 서명 → **통과**
- [ ] 무서명/취소 → fail-closed(미전송) / 거절은 서명 없이 동작
- [ ] 5분 미조작 → **잠금 커튼** → 패스키로 해제

### E. 신선도 / 오프라인
- [ ] serve 잠시 중단 or 데몬 발행 끊기(>30s) → 대시보드 **stale/오프라인**(거짓 신선 아님)

---

## 5. "정상"의 모습
- 데몬·데스크톱 TUI: **무변화**(이 스택은 추가형, 기존 경로 영향 없음).
- 폰 `/autostock`: 실데이터 대시보드 + 5s 갱신 + stale 안전표시 + 패스키 승인/잠금.
- 비인증/무서명 원격: 401/400/405로 거부.
- 데몬 워밍업/중단: 빈-모델·stale (셸 안 깨짐).

---

## 6. 알려진 한계 / 범위 밖
- **차트(자산 곡선/시세/결정 마커)**: 미머지 **F84**. 이 가이드 범위 밖.
- **폰 → 에이전트 프롬프트 전송**: 서버 게이트(S1)는 닫혀 있고, **폰에서 보낸 프롬프트에 클라 서명
  배선이 아직 없어** 현재 거부됨(F79 알려진 한계). 세션 composer 서명 배선은 후속 트랙.
- **day P&L% · buying_power**: 데몬 account block 미발행 → v1 **null**(거짓값 합성 안 함).
  equity·cash·종목 return%·미실현손익은 실값. 채우려면 데몬 `_account_block` 보강(별도 트랙).
- **시장 phase**: `market_open`(bool) 기반 정규장/장마감만. pre/after 세분화는 후속.
- **PWA 설치성/오프라인 셸, 푸시 알림, 신규 수동 주문, 계정 자동detect**: 요구사항상 범위 밖.
- **http-QR ↔ https-passkey 토폴로지 간극**: §2-3 참조 — 본 패스 1순위 확인 항목.

---

## 7. 롤백
- 서버 즉시 무력화: `systemctl --user stop autostock-serve` (+ `disable`). 데몬/TUI 무관.
- tailscale TLS 프론트 해제: `tailscale serve --https=443 off`.
- 코드 롤백(필요 시): F86/F79/F71 머지 커밋 `git revert -m 1 <merge>` — 전부 추가형이라
  다른 경로 무영향. (F79 S1만 빼려면 session.ts `gateRemotePrompt()` 호출 2곳 제거.)

---

## 8. 내가 이미 검증한 것 (작성 시점, 호스트 측 증거)
| 항목 | 명령 | 결과 |
|---|---|---|
| webauthn 서버 로직 | `bun test test/autostock-webauthn.test.ts` (opencode) | **41 pass** |
| dashboard 서버 로직 | `bun test test/autostock-dashboard.test.ts` (opencode) | **15 pass** |
| PWA 애드온 코어 | `bun test --preload ./happydom.ts src/addons/autostock` (app) | **52 pass** (5 files) |
| serve/qr fail-closed | `bun test test/launcher-f71.test.ts` (operator-console) | **13 pass** |
| 라이브 fail-closed | `autostock qr` (비번 미설정) | **거부**: "OPENCODE_SERVER_PASSWORD 미설정 …" |

→ 로직·게이트 분기는 main에서 그린. **남은 것 = §2 셋업(3건) + 폰으로 §4 C/D/E 1회 패스.**
발견되는 버그는 fix 트랙으로 분리(특히 §2-3 토폴로지 간극).

---

## 9. Bring-up 실측 결과 (2026-06-28, 호스트에서 실제 기동)

`vite dev(:3000)` + `autostock serve --cors(:4096)`를 실제로 띄워 와이어 너머로 검증한 결과,
**실기기 이전에 코드 수정이 필요한 블로커**를 발견했다. (Tailscale: PC `100.115.164.25` ↔
폰 `100.102.212.116`, `.env` 비번/origin 설정, `qrcode-terminal` 설치, HTTPS 인증서 활성화까지 완료된 상태)

### 🔴 R1 [BLOCKER] autostock API 라우트가 실제 리스너에 미마운트
- **증상**: 와이어 너머 `GET /autostock/dashboard` → `Content-Type: text/html`(SPA HTML),
  `POST /autostock/webauthn/register-options` → SPA HTML. 즉 **대시보드 데이터 + 패스키
  등록/검증이 네트워크로는 전부 동작 안 함**. (`/doc` 등 타입드 라우트는 200 정상.)
- **근본원인**: `webauthn.route()` + `dashboard-read.route()`는 `Server.Default().app.fetch`
  체인(`opencode/src/server/server.ts:63-68`)에만 마운트됨. 그러나 실제 리스너
  `Server.listen()` → `listenerLayer` → `HttpRouter.serve(createRoutes())`(`server.ts:111`)는
  그 fetch 체인을 **타지 않고** `uiRoute` 캐치올(`/*`)로 떨어뜨림. 단위테스트는 `route()`를
  직접 호출했기에 통과(F86 가이드의 "HTTP 소켓 와이어만 미확인 = 프레임워크 plumbing"이 곧 이 버그).
- **영향**: F71(webauthn 엔드포인트)·F86(대시보드 데이터) 전체가 원격에서 비동작. **블로커.**
- **수정 방향**: autostock route()를 리스너 경로(`createRoutes`)에 `uiRoute` 캐치올보다 **앞에**
  마운트(또는 `listenerLayer`가 동일 `??` 체인을 타도록 래핑). + **리스너를 통과하는** 회귀
  테스트 추가(직접 route() 호출이 아니라 실제 HTTP). Effect HttpRouter 라우트 우선순위 + SPA
  fallback 공존 확인 필요 → 코어 라우팅 변경이라 **트랙 권장.**

### 🟠 R2 [MEDIUM] serve/systemd가 `.env`의 `AUTOSTOCK_WEBAUTHN_ORIGIN`을 전달 안 함
- `OPENCODE_SERVER_PASSWORD`만 `.env`에서 직접 읽음(`serve.ts` `readEnvKey`). `consoleEnv`는
  `process.env` passthrough라 origin이 환경에 export돼 있지 않으면 serve에 전달 안 됨 → webauthn
  fail-closed. systemd 유닛도 `EnvironmentFile` 없음. (이번엔 수동 export로 우회.)
- **수정**: `serveEnv`가 `.env`에서 `AUTOSTOCK_WEBAUTHN_ORIGIN`도 읽어 주입(비번과 동형). 소규모.

### 🟠 R3 [MEDIUM] QR 페이로드가 `http://<ip>:4096`을 굽음
- 패스키는 https 보안 컨텍스트 필요 → http URL은 사용 불가. 폰은 https origin을 수동 입력해야 함.
- **수정**: `tailscale serve` https origin을 굽도록(또는 origin 인자화). 소규모.

### 🟡 R4 [INFO] 배포 토폴로지 미배선 (단일 origin 경로 부재)
- PWA 페이지(`packages/app`, Vite/:3000)와 API(:4096)가 분리. `autostock serve`는 소스 실행이라
  웹 UI를 `app.opencode.ai`로 프록시(우리 `/autostock` 없음) — 임베디드 UI는 컴파일 빌드에만 생성
  (`opencode/script/build.ts:58`, `appDir=packages/app`). 폰이 우리 셸을 받는 "한 origin" 표준
  경로가 없음.
- **방향**: (a) 임베드 빌드로 serve가 단일 포트에 앱+API 서빙, 또는 (b) `packages/app` 정적
  서빙 + 문서화된 단일 origin runbook. R1 수정과 함께 설계.

### ✅ 정상 확인된 것 (와이어 검증)
- CORS preflight: `OPTIONS /autostock/dashboard` → 204 + `Access-Control-Allow-Origin:
  https://vinn-mini.tail49dcde.ts.net` + `Allow-Headers: authorization` (페이지 origin 허용 동작).
- basic-auth: `opencode:<PW>` 200 / 무인증 401 (앱은 `username:"opencode"` 고정 — pairing.ts).
- 데몬 가동 + steering/*.json 실시간 발행(대시보드 데이터 소스는 살아있음 — R1만 풀면 실데이터 나옴).
- vite dev(:3000) 200, `autostock serve --cors` 정상 기동·바인드.

### 결론
R1이 블로커라 **현재 폰 실기기 테스트 불가**. R1~R4가 모두 "모바일 런타임/배포 배선"으로 묶이고
코어 라우팅 변경 + 리스너 통과 테스트가 필요 → **단일 fix 트랙으로 처리 권장**(예: "모바일 실행
경로 배선"). 트랙에서 R1 수정 후 본 가이드 §2-3 토폴로지로 §4 실기기 패스 수행.
</content>
</invoke>
