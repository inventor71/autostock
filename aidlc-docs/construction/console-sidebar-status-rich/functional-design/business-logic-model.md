# F8 Functional Design — Business Logic Model (light)

## BLM-1 — 역할 매핑 (OrderRow.role)
status.py `_order_role` 미러 (콘솔 측 순수 함수):
```
side == BUY                      -> "entry"
order_type in (STOP, STOP_LIMIT) -> "stop-loss"
else                             -> "take-profit"
```
(데몬은 `side`+`order_type` 원시값만 발행; 라벨 파생은 콘솔.)

## BLM-2 — 손익 색/화살표 (D3, status.py `_pnl_markup`)
```
value >= 0 -> green, "▲"
value <  0 -> red,   "▼"
```
적용 대상: PositionRow.unrealized_pnl / pnl_pct, RecentFill(side BUY=green/SELL=red), OrderRow.delta_pct(방향), AccountSummary.open_pnl. 그 외(헤더/역할/심볼)는 v1 색 없음.

## BLM-3 — Δ(트리거까지 거리) 계산
```
current 있으면: delta_pct = (trigger / current - 1) * 100
current 없으면: Δ 공란 (current 미보충 심볼)
```

## BLM-4 — 가격 해소 (PriceBook, status.py `_latest_prices`)
1. 심볼이 보유 포지션이면 `position.current_price` 사용(추가콜 0).
2. 아니면 PriceBook 캐시 조회; 신선하면 사용.
3. 캐시 미스/만료면 슬로우잡이 data client로 보충(best-effort). 실패 시 해당 심볼 current 생략.

## BLM-5 — recent_fills 조립
`get_fills()` → FillEvent 리스트 → `sort(key=ts, reverse=True)[:8]` → `{ts,side,qty,symbol,price}` dict 발행. 슬로우 케이던스(~45s). 빈 결과/실패 → 빈 리스트(블록 숨김).

## BLM-6 — invested
`invested = sum(p.market_value for p in ps.positions.values())` → `_account_block`에 추가.

## BLM-7 — 발행 접합 (publish_snapshot, 5s)
`_build()` 안에서:
- `positions[sym]`에 current_price/market_value/unrealized_pnl 추가(이미 보유한 `ps` 객체에서).
- `open_orders[*]`에 side/order_type 추가 + current_price = (보유 재사용 ∪ PriceBook 캐시).
- `account`에 invested 추가.
- `recent_fills` = 캐시된 최근체결(슬로우잡이 채움), `round_trip`처럼 폴드.
모두 best-effort: 한 부분 실패가 스냅샷 전체를 막지 않음(NFR-4).

## BLM-8 — 케이던스 (확정)
- 5s 발행: 보유가격·주문필드·invested(추가콜 0).
- ~10–15s 슬로우잡: PriceBook(미보유 주문심볼) 보충.
- ~45s 슬로우잡: recent_fills(`get_fills`).
- 콘솔 폴링 1.5s(불변).

## BLM-9 — 하위호환/렌더 (콘솔)
각 신규 필드/블록은 부재 시 숨김(F6 BR-8). 머지 전 데몬 → 신규 표시 없음(정상), **데몬 재시작 필요**.
