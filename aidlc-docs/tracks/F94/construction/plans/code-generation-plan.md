# F94 Code Generation Plan — Unit-1 (콘솔 계좌-read provider-aware)

## A. 코드
- [x] A1. `operator-console/src/alpaca-data.ts` — `formatResponse`를 `export` (스냅샷 경로가
      Alpaca 경로와 동일 포맷 렌더하도록 재사용).
- [x] A2. `operator-console/src/account-truth.ts` 신설 — `createAccountReader({provider,steeringDir,alpaca})`:
      account_farm → `SnapshotAccountReader`(steering/snapshot.json 읽어 account/positions/open_orders),
      그 외 → `AlpacaAccountReader`(기존 AlpacaDataClient 위임, 동작 불변). `isAccountFarm` export.
      degrade: getOrders=open만+안내, getPortfolioHistory=미지원 안내, snapshot 없으면 안내(throw 없음).
- [x] A3. `operator-console/src/mcp-server.ts` — `createAccountReader` 배선(STEERING_DIR +
      AUTOSTOCK_BROKER_PROVIDER), 계좌-truth 5개 핸들러(get_account_info/get_all_positions/
      get_open_position/get_portfolio_history/get_orders)를 `account.*` 경유로 라우팅 + 설명 갱신.
- [x] A4. 시장데이터/참조 툴(assets/calendar/clock + stock bars/quote/trade/snapshot)은 `client.*`
      Alpaca 직결 유지(계좌무관). mutating(close/cancel)은 기존 FileDrop→데몬 경유 유지.

## B. 테스트
- [x] B1. `operator-console/test/account-truth.test.ts` — isAccountFarm(대소문자), account_farm이
      snapshot에서 positions/account/open_position/orders 읽기(HD, RTX/TMO 없음), degrade(orders open-only,
      portfolio-history 안내, snapshot 없음), alpaca/empty는 snapshot 경로 안 탐(client 위임). (5 tests)

## C. Verify
- [x] C1. `bun test ./test` (operator-console) — 187 pass / 0 fail (신규 5 포함).
- [x] C2. 실데이터: 라이브 aggressive 컨테이너 snapshot.json → reader → HD 4 / equity 79,651
      (RTX/TMO 없음) 확인.
- [N/A] 전체 `bun test`는 cli/ 포크 하위까지 긁어 의존성 미설치로 실패(환경, F94 무관) — `./test`로 한정.

## D. 머지 후 (post-merge-guide)
- [ ] D1. F94 머지(main) → /app 코드 반영.
- [ ] D2. 콘솔 재접속(quit→`prod-run.sh attach <name>`): 새 attach가 새 mcp-server(새 코드) 기동.
      데몬 재시작 불필요(콘솔 read는 데몬이 이미 발행하는 snapshot.json만 읽음).
- [ ] D3. 검증: 채팅 "보유 알려줘" → aggressive HD / balanced HON / conservative GILD (RTX/TMO 없음).

## 산출물
- 신규: `operator-console/src/account-truth.ts`, `operator-console/test/account-truth.test.ts`
- 수정: `operator-console/src/mcp-server.ts`, `operator-console/src/alpaca-data.ts`(export)
- 문서: `post-merge-guide.md`
