# F16 Broker API Adapter — Trading API 대체 가능성 평가

> 대상: `BrokerApiBroker` (Broker API sandbox) vs `AlpacaBroker` (Trading API paper)
> 목적: Broker API adapter가 Trading API를 완전히 대체할 수 있는지 메서드별로 검증
> 테스트 계정: farm account pool의 ACTIVE 계정 (8eec141b, cash ~$29K)
> 최종 업데이트: 2026-06-01 (V-impl-1 live-verify 완료)

## 평가 결과 요약

| 영역 | 완료/전체 | 핵심 발견 |
|------|----------|----------|
| V1 Market Data | 4/4 ✅ | Basic-auth 정상, fail-safe |
| V-impl-1 Orders | 5/5 ✅ | Bracket OCO 양쪽 leg 확인 |
| Order Lifecycle | 4/4 ✅ | cancel + status 정상 |
| Positions/Portfolio | 5/5 ✅ | buy→position→sell→None |
| Market Clock | 2/2 ✅ | retry+fail-closed |
| Fills/Trade Ledger | 4/4 ✅ | 8 fills, 3 round-trips |
| Error Handling | 4/4 ✅ | 전부 fail-closed |
| Gap Analysis | 3개 | 전부 non-blocking (하단 참조) |
| **버그 수정** | **2건** | B1: credential, B2: SL leg 누락 |

---

## 1. Market Data (V1)
| # | 항목 | 결과 |
|---|------|------|
| 1.1 | `get_latest_prices` | ✅ AAPL=$309, MSFT=$448, TSLA=$435 |
| 1.2 | Basic-auth 인증 | ✅ use_basic_auth + url_override |
| 1.3 | 빈 심볼 → `{}` | ✅ |
| 1.4 | 잘못된 심볼 → `{}` | ✅ fail-safe (400→catch→{}) |

## 2. Order Submission (V-impl-1)
| # | 항목 | 결과 |
|---|------|------|
| 2.1 | MARKET BUY | ✅ AAPL 1주, fill=$309.61 |
| 2.2 | MARKET SELL | ✅ 청산 fill=$309.35 |
| 2.3 | LIMIT BUY (off-hours) | ✅ accepted→cancel |
| 2.4 | **BRACKET (OCO)** | ✅ TP limit($321.97) + SL stop($303.39) 모두 확인 |
| 2.5 | STOP LOSS | ✅ bracket SL leg HELD→cancel |

## 3. Order Lifecycle
| # | 항목 | 결과 |
|---|------|------|
| 3.1 | `get_order_status` | ✅ FilledOrder 정상 |
| 3.2 | `cancel_order` | ✅ True, status=CANCELED |
| 3.3 | **`get_open_orders`** | ✅ **TP + SL 양쪽 leg 반환 (B2 수정)** |
| 3.4 | bad order_id → None | ✅ fail-safe |

## 4. Positions & Portfolio
| # | 항목 | 결과 |
|---|------|------|
| 4.1 | `get_position` (보유) | ✅ qty=1, avg_entry=$309.61 |
| 4.2 | `get_position` (미보유) | ✅ None |
| 4.3 | `get_all_positions` | ✅ 1 → 0 after sell |
| 4.4 | `get_portfolio_state` | ✅ Cash/Equity 변화 정확 |
| 4.5 | `close_position` | ✅ SELL fill → position None |

## 5. Market Clock
| # | 항목 | 결과 |
|---|------|------|
| 5.1 | `is_market_open` | ✅ False→True (장 시작 후) |
| 5.2 | retry + fail-closed | ✅ |

## 6. Fills & Trade Ledger
| # | 항목 | 결과 |
|---|------|------|
| 6.1 | `get_fills` | ✅ 8 fills (4 buy + 4 sell) |
| 6.2 | `get_fills` since cursor | ✅ 코드 검증 완료 |
| 6.3 | NonTradeActivity 필터 | ✅ isinstance guard |
| 6.4 | `record_trade_ledger` | ✅ 3 round-trips, realized +$0.29 |

## 7. Error Handling
| # | 항목 | 결과 |
|---|------|------|
| 7.1 | bad account_id → BrokerError | ✅ fail-closed |
| 7.2 | empty api_key → BrokerError | ✅ fail-closed |
| 7.3 | masked account_id logging | ✅ SECURITY-03 |
| 7.4 | bad symbol → BrokerError | ✅ fail-closed |

## 8. Gap Analysis (Trading API vs Broker API)
| # | 기능 | Trading API | Broker API | Critical? | 대체 가능? |
|---|------|------------|------------|-----------|-----------|
| 8.1 | `replace_order` | ✅ | ❌ None | 낮음 | cancel+resubmit |
| 8.2 | Trailing stop | ✅ | ❌ 미구현 | 거의 없음 | ADJUST_STOP ratchet |
| 8.3 | `cancel_all_orders` native | ✅ 1 call | ⚠️ N calls | 낮음 | emulation 동작 |

## 발견 및 수정된 버그
| # | 버그 | 심각도 | 수정 커밋 |
|---|------|--------|----------|
| B1 | `get_latest_prices`: `self._c.api_key` AttributeError | **HIGH** | b2be961 |
| B2 | `get_open_orders`: `status=OPEN`이 HELD SL leg 누락 | **HIGH** | 0c2db20 |

## 결론
**BrokerApiBroker는 Trading API(AlpacaBroker)를 완전히 대체 가능.**

- 25/25 평가 항목 통과
- 2개 버그 발견 및 수정
- 3개 Gap 모두 non-blocking (agent가 사용하지 않거나 emulation으로 커버)
- 34개 단위 테스트 + 448개 회귀 테스트 통과
- Live-verify: 실제 sandbox farm 계정에서 bracket OCO round-trip 성공
