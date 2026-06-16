# F86 Post-Merge Guide — 모바일 대시보드 데이터 엔드포인트

> F79 후속: 폰 `/autostock` 대시보드가 **빈-모델 → 실데이터**로 바뀐다. 추가형 read-only 엔드포인트 +
> 클라 폴링. 데몬(python)·데스크톱 TUI·기존 mutating 게이트(F75/F79 S1)는 **무변화**.

## 무엇이 바뀌나 (prod 브랜치)

### 1. 신규 서버 라우트 — `GET /autostock/dashboard` (read-only, 라이브)
- `operator-console/cli/packages/opencode/src/server/autostock/dashboard-read.ts` (신규, fork-isolated).
  `server.ts`의 fetch 체인에 webauthn 다음 1줄로 마운트.
- 데몬이 발행 중인 `steering/{snapshot,health,monitor,pending_approvals}.json`을 읽어 단일 대시보드
  스냅샷 JSON으로 조립해 반환. **브로커 호출 없음**(데몬 캐시 파일만 read).
- **인증**: 기존 basic-auth(`OPENCODE_SERVER_PASSWORD`) + tailscale TLS. 비인증 → 401. read이므로
  패스키 서명 불요(READONLY 정책과 동일선상).
- **fail-safe**: 파일 부재/깨짐/데몬 워밍업 → 부분/빈 200(`published_at:null` → 클라가 stale 표시).
  절대 5xx로 셸을 깨지 않음.

### 2. 모바일 셸 실데이터 (라이브)
- `mobile-shell.tsx`가 진입 시 + **~5s 폴링**으로 위 엔드포인트를 받아 DashboardView에 실데이터 전달
  (잔고·현금·종목별 P&L%·건강·승인대기수·시장세션·에이전트 최근활동). 백그라운드/잠금 시 폴 중단.
  "실시간 데이터 연결은 후속" 고지 문구 제거.
- 신규 `dashboard-source.ts`(순수 매퍼 + 인증 fetch). DashboardView/F79 코어는 **무변경 재사용**.

## 전제 조건
- 콘솔/앱 **재빌드** + `autostock serve` **재시작**(서버 라우트 반영).
- 데몬이 떠서 `steering/snapshot.json` 등을 발행 중이어야 데이터가 보임(없으면 대시보드는 오프라인/빈-모델 = 정상 graceful).
- **신규 env/config 키 없음.** 라우트는 기존 `OPENCODE_SERVER_PASSWORD`/`STEERING_DIR`(없으면 `AUTOSTOCK_ROOT/steering` → repo-root/steering 자동 해석) 사용.

## 실사용 검증 체크리스트 (머지 후, 사용자 1회)
1. **서버 단위(필수)**: `cd operator-console/cli/packages/opencode && bun test test/autostock-dashboard.test.ts` → 13 pass.
   addon: `cd ../app && bun test --preload ./happydom.ts src/addons/autostock` → 52 pass.
2. **로컬 라운드트립(인증)**: serve 기동 후 호스트에서
   `curl -s -u :"$OPENCODE_SERVER_PASSWORD" http://127.0.0.1:<port>/autostock/dashboard | jq .account`
   → equity/cash 실값, `published_at` 존재. **무인증** `curl` → **401**(정상).
   *(머지 전 `route()` 직접호출로 검증 완료: 정상auth→200(실데이터)/무인증·오인증→401/POST→405/타경로→null.
   HTTP 소켓 와이어만 미확인 = 프레임워크 plumbing.)*
3. **잘못된 메서드**: `curl -X POST .../autostock/dashboard` → **405**. *(머지 전 검증 완료.)*
4. **모바일 실기기(핵심)**: 폰 PWA로 `/autostock` 접속 → 대시보드에 **실잔고·포지션·건강·승인대기**가 뜨고
   ~5s마다 갱신. 상단 새로고침 탭 → 즉시 갱신.
5. **신선도 배지**: serve를 잠시 멈추거나 데몬 발행을 끊으면(>30s) → 대시보드 **stale/오프라인 표시**(거짓 신선 아님).
6. **승인·잠금 회귀**: 에이전트 mutating 요청 시 승인 시트, 5분 미조작 잠금 — **F79 그대로 동작**(이 트랙 무영향).

### "정상"의 모습
- 데몬·데스크톱 TUI: 무변화. 폰 `/autostock`: 실데이터 대시보드 + 5s 갱신 + stale 안전표시.
  비인증 요청: 401. 데몬 워밍업/중단: 빈-모델·stale(셸 안 깨짐).

## 튜닝 / 노브
- 폴 주기 `POLL_MS`(기본 5000ms)·신선도 임계 `STALE_THRESHOLD_MS`(기본 30000ms):
  `app/.../addons/autostock/dashboard-source.ts`.
- steering 디렉터리 해석: `STEERING_DIR` env(명시) > `AUTOSTOCK_ROOT/steering` > `<console cwd>/../../steering`.

## 롤백
- `git revert -m 1 <merge>` 1회. 추가형(신규 라우트 + 마운트 1줄 + 클라 배선)이라 다른 경로 무영향.
- 라우트만 끄려면 `server.ts`의 dashboard-read 마운트 1줄 제거(클라는 비-200 → 오프라인 graceful).

## 알려진 한계 / 범위 밖
- **portfolio history / 자산 곡선 / 결정 마커** — 후속 **F84**(모바일 차트). 이 트랙은 데이터 채널만 확립.
- **day P&L % · buying_power** — 데몬 account block 미발행 → **v1 null**(거짓값 합성 안 함). 채우려면 데몬
  `_account_block` 보강(별도 트랙). equity·cash·종목 return%·미실현손익은 실값.
- **시장 phase** — 현재 `market_open`(bool) 기반 정규장/장마감만. pre/after 세분화는 ET 시계 파생 필요(후속).
- **세션 입력 클라 서명 + 세션뷰 모바일 통합** — 별도 후속(F79 고지 그대로).
- **남은 검증(머지 후 검증 세션, 1순위)** — `route()` 라이브(인증/405/경로/실데이터 Response)는 머지 전 완료.
  **남은 것 = 데스크톱 브라우저 `/autostock` 실폴링 + 폰 PWA(tailscale) 실기기** (위 4~6). 신규 코드 없음(F71/75/79
  인프라 재사용). 누적된 모바일 스택 실기기 부채(F71/75/79도 실기기 미검증)와 함께 1회 패스 권장 — 발견 버그는 fix 트랙으로.
