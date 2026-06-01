# F16 Broker API Adapter — Trading API 대체 가능성 평가

> 대상: `BrokerApiBroker` (Broker API sandbox) vs `AlpacaBroker` (Trading API paper)
> 목적: Broker API adapter가 Trading API를 완전히 대체할 수 있는지 메서드별로 검증
> 테스트 계정: farm account pool의 ACTIVE 계정 중 하나 선택

## 평가 항목

### 1. Market Data (V1)
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 1.1 | `get_latest_prices` — 실시간 가격 조회 | AAPL, TSLA, MSFT → 가격 반환 확인 | ✅ AAPL=$311.48, MSFT=$448.17, TSLA=$435.08 |
| 1.2 | `StockHistoricalDataClient` Basic-auth 인증 | broker key/secret으로 sandbox data endpoint 인증 성공 | ✅ use_basic_auth=True + url_override 작동 |
| 1.3 | 빈 심볼 리스트 → 빈 dict (fail-safe) | `get_latest_prices([])` → `{}` | ✅ |
| 1.4 | 존재하지 않는 심볼 처리 | `get_latest_prices(["ZZZ999"])` → `{}` (400→catch→return {}) | ✅ fail-safe, warning log |

### 2. Order Submission (V-impl-1)
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 2.1 | MARKET BUY | ⏸️ 시장 닫힘 (ET 00:52, 6/1 Mon — 9:30 ET open) | ⏸️ 대기 |
| 2.2 | MARKET SELL (청산) | ⏸️ 2.1 fill 후 테스트 | ⏸️ 대기 |
| 2.3 | LIMIT BUY | AAPL limit $155.74 → accepted, 5s poll timeout → status=accepted | ✅ order lifecycle OK |
| 2.4 | BRACKET (OCO) | ⏸️ 시장 열린 후 테스트 | ⏸️ 대기 |
| 2.5 | STOP LOSS | ⏸️ 시장 열린 후 테스트 | ⏸️ 대기 |

### 3. Order Lifecycle
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 3.1 | `get_order_status` | LIMIT BUY order ID 조회 → FilledOrder (filled_price=0) | ✅ |
| 3.2 | `cancel_order` | LIMIT BUY cancel → True, status=CANCELED | ✅ |
| 3.3 | `get_open_orders` | open order 1개 → leg flattening | ✅ (1→0 after cancel) |
| 3.4 | 존재하지 않는 order_id → None | `get_order_status("bad-id")` → None (warning log) | ✅ fail-safe |

### 4. Positions & Portfolio
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 4.1 | `get_position` — 보유 포지션 | ⏸️ fill 필요 | ⏸️ 대기 |
| 4.2 | `get_position` — 미보유 → None | `get_position("AAPL")` → None | ✅ |
| 4.3 | `get_all_positions` — 전체 | 0 positions (no trading history) | ✅ |
| 4.4 | `get_portfolio_state` | Cash=$29,392.69, Equity=$29,392.69, Positions=0 | ✅ |
| 4.5 | `close_position` | ⏸️ fill 필요 | ⏸️ 대기 |

### 5. Market Clock
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 5.1 | `is_market_open` — 장 시간 | ET 00:52 → False (next_open=09:30 ET) | ✅ |
| 5.2 | retry + fail-closed | False 반환, 예외 없음 (SECURITY-15) | ✅ |

### 6. Fills & Trade Ledger
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 6.1 | `get_fills` — fill 이벤트 | 0 fills (거래 내역 없음 — 정상) | ✅ 구조 정상 |
| 6.2 | `get_fills` — since cursor | 거래 내역 없어서 skip | ⏸️ fill 발생 후 |
| 6.3 | `get_fills` — NonTradeActivity 필터링 | `_to_fill_event_typed` isinstance guard | ✅ 코드 확인 |
| 6.4 | `record_trade_ledger` | ⏸️ round-trip fill 필요 | ⏸️ 대기 |

### 7. Error Handling & Edge Cases
| # | 항목 | 방법 | 결과 |
|---|------|------|------|
| 7.1 | 잘못된 account_id → BrokerError | 존재하지 않는 UUID → APIError (fail-closed) | ✅ |
| 7.2 | 빈 api_key → BrokerError | `api_key=""` → BrokerError | ✅ |
| 7.3 | 로그에 account_id 마스킹 (SECURITY-03) | `id=8eec141b…` (앞 8자만) | ✅ |
| 7.4 | `submit_order` 잘못된 심볼 → BrokerError | `ZZZ999` → BrokerError | ✅ fail-closed |

### 8. Gap Analysis
| # | 기능 | Trading API | Broker API | Gap |
|---|------|-------------|------------|-----|
| 8.1 | `replace_order` | ✅ 구현 | ❌ 미구현 (None) | Broker API에 replace endpoint 없음 |
| 8.2 | Trailing stop | ✅ 지원 | ❌ 미구현 | Broker API request 클래스에 없음 |
| 8.3 | `cancel_all_orders` (native) | ✅ 네이티브 | ⚠️ emulate (loop cancel) | 동작 동등 |

## 평가 진행 순서
1. V1: Market Data (4개 항목) — 의존성 없음, 단독 실행 가능
2. 기본 주문(MARKET BUY/SELL) → position/portfolio → fills/ledger
3. 고급 주문(LIMIT/BRACKET/STOP) → open_orders/cancel
4. Market clock → error handling → gap analysis
