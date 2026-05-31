# F8 NFR Design — Patterns

F6/F4의 발행 패턴을 그대로 따르고, 신규 fetch 2종(PriceBook, recent_fills)을 슬로우잡으로 분리.

## P1 — 가산적 스냅샷 확장 (단일 발행자)
`publish_snapshot._build()`(5s, 워커)는 이미 보유한 `ps`/`opens`에서 신규 필드를 **추출만** 추가(보유 current_price/market_value/unrealized_pnl, account.invested). 추가 브로커콜 0. `last_snapshot` 인메모리 미러 유지(F3 critic#4). 부분 실패 → 해당 키 생략, 발행 계속(NFR-4).

## P2 — PriceBook (미보유 주문심볼 가격, 슬로우잡 + 캐시)
- 자료구조: `dict[str, tuple[float, datetime]]` (symbol → price, fetched_at). 워커 소유, 단일 스레드 접근(락 불필요, NFR-2).
- 슬로우잡 `refresh_order_prices`(APScheduler add_seconds_job **12s**): open_orders 심볼 ∖ 보유 심볼만 모아 `StockHistoricalDataClient.get_stock_latest_trade`로 일괄 보충(status.py `_latest_prices`), `fetched_at` 갱신. 빈 집합이면 콜 0.
- TTL: 30s(2주기). publish_snapshot은 보유 current_price 우선, 없으면 신선한 캐시값 접합, 둘 다 없으면 생략(Δ 공란).
- best-effort: 실패 → 캐시 유지/생략, 예외 전파 금지.

## P3 — recent_fills (슬로우잡)
- 슬로우잡 `refresh_recent_fills`(add_seconds_job **45s**, round_trip 잡과 동급): `broker.get_fills()` → ts desc top-8 → `{ts,side,qty,symbol,price}` dict 캐시(`self._recent_fills`). publish_snapshot이 폴드(round_trip 패턴 그대로).
- `refresh_round_trip`와 같은 `get_fills` 호출원 — 가능하면 한 잡에서 둘 다 산출(콜 1회 재사용) 검토.

## P4 — 동시성/경계
| 스레드 | 접근 | 비고 |
|---|---|---|
| CommandBus 워커 | broker/data, PriceBook, recent_fills 캐시, last_snapshot | 단일 직렬(NFR-2) |
| APScheduler | 잡 트리거만(_build/refresh를 워커에 submit) | 기존 패턴 |
| 콘솔 프로세스 | snapshot.json 읽기 | NFR-1 |
신규 동시성 프리미티브 0.

## P5 — 콘솔 렌더 (TS, 순수 파생)
역할/색/Δ/pnl%는 콘솔 순수 함수(BLM-1~3) — PBT/단위테스트 대상. 필드 부재 시 숨김(BR-2). `wrapMode="word"` + width-floor(P6).

## P6 — width floor
드래그/`AUTOSTOCK_SIDEBAR_WIDTH` clamp 하한 **24 → 36**. 1줄 행 핵심 필드(심볼·수량·pnl%)가 36칸에서 잘리지 않음을 기준. 상한 120 유지.

## P7 — 보안 (SECURITY-03/15)
스냅샷/캐시에 가격·수량·심볼만(비밀값 없음). fetch 예외 fail-closed.
