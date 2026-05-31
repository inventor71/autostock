# F8 Code Generation — Part 1 Plan (`console-sidebar-status-rich`)

승인 시 Part 2 첫 동작 = `git worktree add … -b feat/console-sidebar-status-rich main`. 신규 런타임 의존성 0.

## Step 0 — worktree
- [ ] `git worktree add .claude/worktrees/sidebar-status-rich -b feat/console-sidebar-status-rich main`
- [ ] 서브모듈 `operator-console/cli` 동기화(현 핀 `7d26d49`).

## Step 1 — (Python) 공유 헬퍼 + 정확 필드 재확인
- [ ] 도구 안정 상태에서 `src/core/types.py`(Position/PortfolioState/Order/OrderSide/OrderType), `equity_log.snapshot`, `get_fills`/FillEvent grep으로 필드명 확정.
- [ ] `_order_role` 동등 로직 위치 결정(status.py에서 공유 유틸로 추출 vs 콘솔 전용 파생). v1은 **콘솔 파생**(데몬은 side+order_type 원시값만) → Python 추출 불필요면 생략.

## Step 2 — (Python) `publish_snapshot` 가산 확장
- [ ] `positions[sym]`에 `current_price/market_value/unrealized_pnl` 추가(`ps`에서 추출).
- [ ] `open_orders[*]`에 `side`(OrderSide.value)/`order_type`(OrderType.value) 추가.
- [ ] `_account_block`에 `invested = Σ market_value` 추가.
- [ ] best-effort/가산적(NFR-4) — 기존 키 불변.

## Step 3 — (Python) PriceBook 슬로우잡 (미보유 주문심볼, 12s)
- [ ] `SteeringRuntime`에 `_price_book: dict[str,(float,datetime)]` + `refresh_order_prices()`(워커 submit).
- [ ] open_orders 심볼 ∖ 보유 심볼만 `StockHistoricalDataClient.get_stock_latest_trade` 일괄 보충, TTL 30s.
- [ ] `publish_snapshot`이 `open_orders[*].current_price` = 보유 재사용 ∪ 신선 캐시값 접합(없으면 생략).
- [ ] 스케줄러 `add_seconds_job(refresh_order_prices, 12)`.

## Step 4 — (Python) recent_fills 슬로우잡 (45s)
- [ ] `_recent_fills` 캐시 + `refresh_recent_fills()`: `get_fills()`→ts desc top-8 → `{ts,side,qty,symbol,price}`.
- [ ] `refresh_round_trip`과 `get_fills` 호출 공유 가능하면 통합(콜 1회).
- [ ] `publish_snapshot`이 `recent_fills` 폴드. `add_seconds_job(refresh_recent_fills, 45)`.

## Step 5 — (TS) 스키마 미러 + contract
- [ ] `operator-console/src/schema.ts`에 신규 필드 타입.
- [ ] `operator-console/contract/` 골든 샘플 갱신 + 크로스랭귀지 contract 테스트.

## Step 6 — (TS) 사이드바 렌더 (`autostock.tsx`)
- [ ] FC-1 보유: 평단/현재가/평가손익$/% + green·red·▲▼.
- [ ] FC-2 주문: side/역할(파생)/트리거/현재가/Δ% + 방향색.
- [ ] FC-3 최근 체결 블록(신규): 시각/side색/수량/심볼/체결가.
- [ ] FC-4 요약: invested 추가.
- [ ] FC-5 1줄 압축 + `wrapMode="word"`; 필드 부재 시 숨김(BR-2).
- [ ] 순수 파생 함수(role/pnl%/Δ/색) 분리 → 단위테스트.

## Step 7 — (TS) width floor
- [ ] `sidebar-width.ts` clamp 하한 24→36(상한 120 유지).

## Step 8 — 테스트
- [ ] Python: PBT(pnl%/Δ%/역할/정렬·top-N) + publish_snapshot 신규필드 + 슬로우잡 best-effort/캐시 TTL. 전체 회귀(현 366 기준 무회귀).
- [ ] TS: bun 단위(role/색/Δ/숨김) + contract. (서브모듈 미설치면 명시 파일만 실행.)

## Step 9 — 빌드/검증/핀
- [ ] tsgo 타입체크(서브모듈 deps 설치 가능 시).
- [ ] 라이브: R1 데몬 재시작 후 4블록+색, R2 미보유 주문심볼 Δ, R3 드래그 wrap+floor.
- [ ] 서브모듈 커밋 + 부모 재핀(머지/푸시는 사용자 게이트 — 외부 영향).

## 충돌/주의
- F7(copy/tips)도 콘솔 편집 — F8은 `autostock.tsx`/`schema.ts`/`sidebar-width.ts` 중심, 겹침 최소. 머지 시 조율.
- 데몬 재시작 필요(BR-8). 콘솔 읽기전용 불변(NFR-1).

**게이트: 이 Part1 계획 승인 → worktree 생성 + 코딩 시작(자율).**
