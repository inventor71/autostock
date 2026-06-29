# F94 Requirements — 콘솔 계좌-truth 읽기 툴 provider 정합성 (F92 TS판 후속)

**Depth**: standard · **Type**: bugfix · **Brownfield**

## 1. 문제 (확인됨, 라이브)
F92가 Python 데몬/CLI broker-truth를 provider-aware `create_broker`로 통일했으나 sweep이
Python만 훑어 **TypeScript 콘솔 경로**를 놓쳤다. operator-console의 채팅 "live" 계좌-read
툴이 `operator-console/src/alpaca-data.ts`(ALPACA_API_KEY → `paper-api.alpaca.markets` 직결)로
Alpaca 계좌를 직접 읽어, **account_farm 인스턴스가 자기 sub-account가 아니라 공유 Alpaca
계좌(유령 RTX/TMO, eq 99,939)**를 보고한다.

증상: aggressive 콘솔에서 사이드바는 HD(snapshot.json=데몬 account_farm 진실)인데, 채팅으로
"보유 알려줘"(→`get_all_positions`) 하면 RTX/TMO(+$461.70) 반환.

## 2. 영향 지점 (TS 전수 점검 결과)
유일한 Alpaca-직결 **계좌-read** 경로 = `operator-console/src/mcp-server.ts`가 쓰는
`AlpacaDataClient`(alpaca-data.ts). 대상 메서드/툴:
- `getAccountInfo` (get_account_info, mcp:263) — 계좌 equity/cash 등
- `getAllPositions` (get_all_positions, mcp:273)
- `getOpenPosition` (get_position, mcp:285)
- `getPortfolioHistory` (mcp:299)
- `getOrders` (get_orders, mcp:365)

**계좌무관(시장데이터/참조 — 유지)**: getAsset/getAllAssets/getCalendar/getMarketClock +
getStockBars/LatestBar/LatestQuote/LatestTrade/Quote/Snapshot/Trades. (Alpaca 직결 정상.)

**안전(변경 없음)**:
- mutating 툴(close_position/close_all_positions/cancel_order) → `handleStructured→FileDrop→데몬`
  경유 → account_farm로 올바르게 실행.
- `dashboard-read.ts`(F86 모바일 대시보드) → snapshot.json 경유(이미 정합). webauthn → Alpaca client 미사용.

## 3. 데몬 진실 소스
`<STEERING_DIR>/snapshot.json` (데몬이 ~주기적으로 발행, account_farm 진실):
keys: `positions{sym:{qty,avg_entry_price,side,current_price,market_value,unrealized_pnl}}`,
`open_orders[{symbol,order_id,stop_price,limit_price,side,order_type,current_price}]`,
`account{equity,cash,invested,open_pnl,position_count}`, `published_at` 등.

## 4. 목표 / 수용 기준
1. **provider-aware 라우팅**: 계좌-read 5개 툴이 `AUTOSTOCK_BROKER_PROVIDER==="account_farm"`이면
   **데몬 snapshot.json** 경유로 답하고, 그 외(alpaca/빈값)는 기존 Alpaca 직결 유지.
   - AC: aggressive 콘솔 채팅 `get_all_positions` → HD 4주 (RTX/TMO 없음), `get_account_info` →
     eq 79,651. balanced=HON9, conservative=GILD14.
   - AC: alpaca provider 인스턴스(있다면)는 동작 불변(Alpaca 직결).
2. **시장데이터 툴 불변**: Alpaca 직결 유지(계좌무관, 공유 정상).
3. **degrade 처리**(snapshot에 없는 것):
   - `getOrders`의 closed/history 필터: snapshot은 open_orders만 → account_farm에선 open만
     반환 + "히스토리는 미지원(사이드바/데몬 참조)" 명시.
   - `getPortfolioHistory`: snapshot에 없음 → account_farm에선 "미지원" 안내(또는 사이드 소스).
4. **freshness 표기**: account_farm 경로는 "데몬 snapshot 기준(±발행주기)"임을 응답/설명에 명시
   (기존 'live Alpaca' 문구는 alpaca일 때만 유효).
5. **회귀 방지 테스트**: provider별 라우팅 단위테스트(account_farm→snapshot 파싱/포맷,
   alpaca→client 위임). `operator-console/test/`에 추가(bun test).
6. **배포**: `bun run dev`는 소스 직실행 → 빌드 없이 재attach로 반영. 라이브 검증.

## 5. 비목표 (Out of Scope)
- 시장데이터 공유 구조(정상).
- mutating 경로(이미 데몬 경유로 정합).
- account_farm을 TS에서 직접 API로 재구현(데몬 snapshot 재사용으로 충분).
- F93 모바일 트랙 작업(operator-console 겹침은 머지 시 조율).

## 6. 미결정 (Requirements UAQ)
- portfolio-history / order-history(closed)의 account_farm degrade 방식(안내 vs equity.jsonl 등 대체 소스).
- 별건: 무관리로 남은 옛 Alpaca 계좌의 RTX/TMO + resting order flatten/cancel 여부.
- 확장(Security/PBT) opt-in.
