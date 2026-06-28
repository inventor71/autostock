# F93 Post-Merge Guide — 모바일 실행 경로 배선 fix

> 이 머지분으로 **폰에서 모바일 PWA가 실제로 동작 가능**해진다(이전엔 와이어 너머 `/autostock/*`가
> 전부 SPA HTML로 떨어져 대시보드/패스키가 죽어 있었음). 데몬·데스크톱 TUI·기존 타입드 라우트는 무변화.

## 무엇이 바뀌나 (prod 브랜치)
1. **R1**: `autostock` API 라우트(`/autostock/dashboard` GET, `/autostock/webauthn/*`)가 실제 리스너
   (`Server.listen`→`createRoutes`)에 마운트됨 → 와이어 너머로 **JSON** 반환(이전 SPA HTML). `/autostock`
   셸 페이지와 그 외 경로는 그대로 SPA fallback. `/doc` 등 타입드 라우트 무영향.
2. **R2**: `autostock serve`가 루트 `.env`의 **`AUTOSTOCK_WEBAUTHN_ORIGIN`을 자동 전달**(이전엔 비번만
   .env에서 읽어, origin을 환경에 export하지 않으면 패스키가 fail-closed였음). systemd 유닛도 동일
   (유닛이 launcher `serve`를 실행).
3. **R3**: `autostock qr` 페어링 url이 **https origin**(`AUTOSTOCK_WEBAUTHN_ORIGIN`)을 우선 사용. 미설정
   시 `http://<ip>:4096`로 폴백하며 **경고**로 https 필요성 고지(패스키는 secure context 필수).
4. **R4(문서)**: 아래 검증된 두 origin runbook. 코드 변경 없음.

**신규 env/config 키 없음** (기존 `OPENCODE_SERVER_PASSWORD` / `AUTOSTOCK_WEBAUTHN_ORIGIN` 사용).

## 전제 조건
- 콘솔/앱 재빌드 불필요(소스 실행). `autostock serve` **재시작**으로 새 라우트/서버 반영.
- `.env`: `OPENCODE_SERVER_PASSWORD`, `AUTOSTOCK_WEBAUTHN_ORIGIN=https://<host>.<tailnet>.ts.net`.
- Tailscale up(PC+폰), Tailscale **HTTPS 인증서 활성화**(admin), 데몬 가동(steering 발행).

## 단일 origin이 아님 — 검증된 두 origin runbook (R4)
PWA 페이지(`packages/app`, Vite)와 API(opencode `serve`)는 별도 서버다. 폰이 패스키까지 쓰려면 둘 다
https여야 하고 page origin = `AUTOSTOCK_WEBAUTHN_ORIGIN`이어야 한다.

```bash
# 1) API: 풀 배선 + tailnet 바인드 + CORS(페이지 origin 허용)
autostock serve --cors https://<host>.<tailnet>.ts.net     # :4096, .env에서 origin 자동 전달(R2)

# 2) PWA 페이지: vite (빌드 or dev)
cd operator-console/cli/packages/app && bun run dev --port 3000 --host 0.0.0.0

# 3) tailscale serve — 두 https origin (HTTPS 인증서 활성화 필요)
tailscale serve --bg --https=443  http://127.0.0.1:3000     # 페이지 → https://<host>.ts.net
tailscale serve --bg --https=8443 http://127.0.0.1:4096     # API   → https://<host>.ts.net:8443
```
- 폰: 브라우저로 `https://<host>.<tailnet>.ts.net/autostock` 열기 → 서버 추가(QR 또는 수동) url=
  `https://<host>.<tailnet>.ts.net:8443`, 비번=`OPENCODE_SERVER_PASSWORD`, username=`opencode` → 패스키 등록.
- `autostock qr`는 이제 https origin(:443 page origin)을 굽는다. API가 :8443이면 폰에서 **API url만
  :8443로 보정**해 등록(또는 page+API를 한 origin 경로 라우팅으로 합치는 단일-origin 패키징은 후속 트랙).

## 실사용 검증 체크리스트 (폰, 1회)
1. **API 라이브(호스트)**: `curl -u opencode:$OPENCODE_SERVER_PASSWORD http://127.0.0.1:4096/autostock/dashboard | jq .account`
   → **JSON 실값**(HTML 아님). 무인증 → 401, POST → 405. `…/webauthn/register-options`(POST) → JSON challenge.
2. **폰 셸**: `/autostock` 접속 → 셸 + **대시보드 실데이터 5s 갱신**(잔고/포지션/건강/승인대기).
3. **패스키**: mutating 도구 요청 → 승인 시트 → 지문 서명 통과. 무서명 거부. 5분 잠금.
4. **신선도**: serve/데몬 중단 >30s → stale 표시.
5. **회귀**: 데스크톱 TUI/데몬 자동 턴 무변화.

### "정상"의 모습
- 와이어 너머 `/autostock/dashboard` = JSON 실데이터, `/autostock` 셸 = SPA, 패스키 등록/승인 동작.
- 비인증 401, 데몬 워밍업 시 빈-모델 stale(셸 안 깨짐).

## 롤백
- `git revert -m 1 <merge>` 1회. 전부 추가형(라우트 마운트 + launcher env/QR + 테스트)이라 다른 경로 무영향.
- 라우트만 끄려면 `createRoutes`의 `autostockRoute` 제거(다시 SPA로 폴백). serve env/QR 변경은 무해(폴백 보존).

## 알려진 한계 / 범위 밖
- **단일 origin 패키징**(임베드 빌드 or serve가 app dist 정적 서빙) — 후속 트랙. 현재는 두 origin runbook.
- **폰→에이전트 프롬프트 클라 서명**(F79 한계), **F84 차트**, **day P&L%/buying_power**(데몬 미발행) — 범위 밖.
- `httpapi-listen.test.ts` 로그 테스트의 full-file flaky 실패 — **base에서도 실패**하는 F93 무관 기존 결함.
</content>
