# F8 Functional Design — Domain Entities (light)

유닛 `console-sidebar-status-rich`. UI 있음 → frontend-components.md 동반. 필드는 `scripts/status.py` + `src/agent/steering/runtime.py::publish_snapshot`에 그라운딩.

## E1 — PositionRow (보유 상세, FR-1)
사이드바 보유 행 1개.
| 필드 | 출처 | 비고 |
|---|---|---|
| symbol | `snapshot.positions` key | |
| qty | `positions[sym].qty` | 기존 |
| avg_entry_price | `positions[sym].avg_entry_price` | 기존 |
| current_price | **신규** `positions[sym].current_price` | `PortfolioState.positions[*].current_price`에 이미 존재 → 추출만 |
| market_value | **신규** `positions[sym].market_value` | 동상 |
| unrealized_pnl | **신규** `positions[sym].unrealized_pnl` | 동상 |
| pnl_pct | 콘솔 파생 `current/avg-1` | 발행 안 함 |

## E2 — OrderRow (주문 상세, FR-2)
미체결 주문 행 1개.
| 필드 | 출처 | 비고 |
|---|---|---|
| symbol | `open_orders[*].symbol` | 기존 |
| side | **신규** `open_orders[*].side` (`OrderSide.value`) | |
| role | 콘솔 파생: BUY→entry, STOP/STOP_LIMIT→stop-loss, else take-profit | status.py `_order_role` 미러 |
| trigger | `limit_price ?? stop_price` | 기존(필드 둘 다 발행 중) |
| order_type | **신규** `open_orders[*].order_type` (`OrderType.value`) | role 파생용 |
| current_price | **신규** `open_orders[*].current_price` | 보유분 재사용 + 미보유 보충(E5) |
| delta_pct | 콘솔 파생 `(trigger/current-1)*100` | current 없으면 공란 |

## E3 — RecentFill (최근 체결, FR-3)
| 필드 | 출처 |
|---|---|
| ts (HH:MM) | `recent_fills[*].ts` |
| side | `recent_fills[*].side` |
| qty | `recent_fills[*].qty` |
| symbol | `recent_fills[*].symbol` |
| price | `recent_fills[*].price` |

발행: **신규** `snapshot.recent_fills` = `broker.get_fills()`(F3/F6 FillEvent) → ts 내림차순 상위 N(=8). 기존 일시적 `snapshot.fills`(웨이크용)와 **별개**(그건 cursor 이후 새 체결만).

## E4 — AccountSummary (요약, FR-4)
| 필드 | 출처 | 비고 |
|---|---|---|
| equity, cash, open_pnl, position_count | `_account_block` (equity_log.snapshot) | 기존 |
| invested | **신규** `Σ positions[*].market_value` | status.py `_summary` invested |

## E5 — PriceBook (데몬 내부, FR-2/D4)
미보유 주문심볼의 현재가 캐시. `symbol -> (price, fetched_at)`. status.py `_latest_prices` 패턴: 보유 포지션 `current_price` 우선 재사용, 없는 심볼만 data client로 보충, 슬로우 케이던스로 갱신. 콘솔에 직접 노출 안 됨 — `open_orders[*].current_price` 접합에만 사용.

## 메인 재사용 경계 (신규 동시성 프리미티브 0)
- 발행/브로커/data 접근 = 단일 CommandBus 워커(NFR-2, 기존).
- `_account_block`(equity_log.snapshot), `get_fills`(F3/F6), `get_portfolio_state`/`get_open_orders`(기존) 재사용.
- 콘솔은 `snapshot.json`만 읽음(NFR-1) — 신규 필드는 전부 가산적.
