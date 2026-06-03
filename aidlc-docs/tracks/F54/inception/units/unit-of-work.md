# Units of Work — F54 숏 포지션 기능

> **Date**: 2026-06-04

## Unit A: Trading Core (숏 주문 실행 파이프라인)

**Goal**: 시스템이 숏 주문을 안전하게 접수, 검증, 실행할 수 있게 한다.

**Files**:
| # | File | Change |
|---|------|--------|
| 1 | `src/core/types.py` | Signal/OrderSide에 SELL_SHORT, BUY_TO_COVER 추가 |
| 2 | `src/core/models.py` | Position.side 추가, P&L 수정, Order validator 확장 |
| 3 | `src/risk/manager.py` | _handle_sell_short, _handle_buy_to_cover, inverted bracket/stop/target/ratchet/polled, dual circuit breaker, auto-flip gate |
| 4 | `src/risk/position_sizer.py` | Short margin awareness |
| 5 | `src/execution/base.py` | OrderSide.SELL_SHORT/BUY_TO_COVER 지원 명시 |
| 6 | `src/execution/brokers/alpaca_broker.py` | SELL_SHORT→AlpacaSide.SELL_SHORT, BUY_TO_COVER→BUY_TO_COVER, Position.side 보존 |
| 7 | `src/execution/brokers/simulated.py` | Short position tracking |
| 8 | `src/agent/executor.py` | _to_signal() 숏 매핑, auto-flip(FR-3), _place_protection() direction-aware |
| 9 | `src/agent/journal.py` | DecisionAction 확장 |

**Dependencies**: None (foundational layer)

## Unit B: Agent Intelligence (숏 분석 + 의사결정)

**Goal**: LLM 에이전트가 숏 기회를 분석하고 의사결정할 수 있게 한다.

**Files**:
| # | File | Change |
|---|------|--------|
| 1 | `src/agent/tools/market.py` | short_interest, borrow_rate, locate 데이터 |
| 2 | `src/agent/prompts.py` | Research/intraday/EOD/wake 프롬프트 숏 컨텍스트 |
| 3 | `src/agent/orchestrator.py` | held_symbols에 숏 포지션 포함 |
| 4 | `workspace/CLAUDE.md` | 숏 트레이딩 규칙 섹션 |
| 5 | `src/agent/steering/commands.py` | `/short`, `/cover` 명령 |
| 6 | `src/agent/steering/records.py` | SELL_SHORT/BUY_TO_COVER action verbs |
| 7 | TUI (해당 파일) | L/S 마커 + P&L 반전 |

**Dependencies**: Unit A (RiskManager, Broker, Executor interface)
