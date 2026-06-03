# F8 NFR Design — Logical Components

## Python (데몬, worktree off main)
| 컴포넌트 | 위치 | 변경 |
|---|---|---|
| `publish_snapshot._build` | `src/agent/steering/runtime.py` | positions에 current_price/market_value/unrealized_pnl; open_orders에 side/order_type/current_price; account에 invested; recent_fills 폴드 |
| `_account_block` | runtime.py | invested(Σ market_value) 추가 |
| `refresh_order_prices` (신규) | runtime.py | 12s 슬로우잡, PriceBook 캐시 보충(미보유 주문심볼), `StockHistoricalDataClient` 재사용 |
| `refresh_recent_fills` (신규) | runtime.py | 45s 슬로우잡, `get_fills`→top-8 캐시 (가능 시 refresh_round_trip과 호출 공유) |
| 역할/가격 헬퍼 (신규/공유) | `src/.../?` (status.py 로직 추출 검토) | `_order_role`/가격해소 공유 — 중복 방지 |
| 잡 등록 | `src/trading/modes/agent.py` (스케줄러 와이어링) | add_seconds_job(refresh_order_prices 12s, refresh_recent_fills 45s) |

데이터 타입(이미 존재, 확인용): `Position.{qty,avg_entry_price,current_price,market_value,unrealized_pnl}`, `PortfolioState.{equity,cash,positions,position_count}`, `Order.{symbol,side,order_type,limit_price,stop_price}`, `OrderSide.{BUY,SELL}.value`, `OrderType.{LIMIT,STOP,STOP_LIMIT}.value`, `FillEvent.{fill_id,symbol,side,qty,price,ts}`. (Code Gen Part2에서 정확 필드명 재확인 — 도구 안정 시 grep.)

## TS (콘솔, 서브모듈 `operator-console/cli`)
| 컴포넌트 | 위치 | 변경 |
|---|---|---|
| 스키마 미러 | `operator-console/src/schema.ts` | positions/open_orders/account/recent_fills 신규 필드 타입 |
| 사이드바 렌더 | `.../tui/feature-plugins/sidebar/autostock.tsx` | FC-1~5: 보유/주문/최근체결/요약 확장 + green/red·▲▼ + 1줄압축/wrap |
| width clamp | sidebar width 모듈(F6 `sidebar-width.ts`) | floor 24→36 |
| 순수 파생 | autostock.tsx 또는 헬퍼 | role/pnl%/Δ/색 함수 |
| contract | `operator-console/contract/` | 골든 샘플에 신규 필드(F4 Phase4) |

## 테스트
- Python: PBT(pnl%/Δ%/역할/recent_fills 정렬·top-N) + publish_snapshot 신규필드 단위 + 슬로우잡 best-effort/캐시.
- TS: bun 단위(role/색/Δ/숨김) + contract.
- 라이브(R): R1 데몬 재시작 후 사이드바 보유/주문/체결/색 확인, R2 미보유 주문심볼 Δ 보충, R3 드래그 wrap + floor.

## Infra
SKIP (로컬 데몬/TUI).
