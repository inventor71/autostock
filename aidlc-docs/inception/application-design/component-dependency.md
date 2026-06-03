# F30 Application Design — Component Dependencies

## Dependency Matrix

| Component | Depends On | Relation | Type |
|---|---|---|---|
| **KisBroker** | BaseBroker (src/execution/base.py) | Implements | Build-time |
| | Order, Position, PortfolioState, FilledOrder, OpenOrder, FillEvent | Uses | Build-time |
| | KIS SDK (kis_auth) | Uses | Runtime |
| | install_session_timeout (src/execution/brokers/session_timeout.py) | Uses | Runtime |
| **KisDataProvider** | BaseDataProvider (src/data/base.py) | Implements | Build-time |
| | TimeFrame (src/core/types.py) | Uses | Build-time |
| | KIS SDK (kis_auth) | Uses | Runtime |
| **DecisionExecutor** (MOD: 1곳) | BaseBroker.halt_reference_symbol | Reads | Runtime |
| | RiskManager (src/risk/manager.py) | Uses | Runtime |
| | Journal (src/agent/journal.py) | Uses | Runtime |
| **TradingScheduler** (MOD) | APScheduler (CronTrigger) | Uses | Runtime |
| **AgentTradingMode** (MOD) | KisBroker, TradingScheduler | Uses | Runtime |

## Data Flow

```
[Agent] ──decisions.jsonl──→ [DecisionExecutor]
                                  │
                    ┌─────────────┼─────────────┐
                    │ KIS 확인     │              │
                    v             v              v
               BUY/SELL        HOLD       ADJUST_STOP
                    │        (no-op)       (no-op)
                    v
            [RiskManager]
            (bracket=False)
                    │
                    v
              _simple_buy()
              _simple_sell()
                    │
                    v
            [KisBroker]
            submit_order()
                    │
                    v
            KIS 국내주식 API
                    │
                    v
            [Market: KOSPI/KOSDAQ]
                    │
                    v
            fill 확인 (polling)
                    │
                    v
            run_polled_exits()
            check_stop_loss()
            check_take_profit()
                    │
                    v
            KisBroker.close_position()
            (지정가 청산)
```

## Communication Patterns

| Component Pair | Pattern | Notes |
|---|---|---|
| AgentTradingMode → KisBroker | Direct injection (constructor) | AlpacaBroker와 동일 패턴 |
| AgentTradingMode → KisDataProvider | Direct injection | AlpacaDataProvider와 동일 |
| DecisionExecutor → KisBroker | Property check (`supports_bracket_orders`) | Runtime capability detection |
| TradingScheduler → KST | Parameterized timezone | 기존 US Eastern도 유지 |
| KisBroker → KIS API | REST (SDK wrapping) | Token-based auth, rate limited |
| KisDataProvider → KIS API | REST (SDK wrapping) | Same session, separate rate limit |

## Key Design Decision: Capability-Based Runtime Branching

```
BaseBroker (ABC)
    └── halt_reference_symbol: str = "SPY"     ← NEW (서킷브레이커 지수)

    AlpacaBroker:    halt="SPY"     native bracket/OCO
    SimulatedBroker: halt="SPY"     native bracket/OCO
    KisBroker:       halt="069500"  EMULATED bracket/OCO (스탑지정가+지정가 resting + reconcile)

DecisionExecutor: (Option B — 변경 최소화)
    # bracket 검증/_place_protection/_adjust_stop 모두 변경 없음
    # (KIS는 use_bracket_orders=True, KisBroker가 OCO/STOP emulate)
    _update_market_halt(): broker.halt_reference_symbol 참조  ← 유일한 변경

RiskManager: 변경 없음 (시장가 ORD_DVSN=01 그대로 전달)

KisBroker.submit_order():  ← 복잡도가 여기로 집중
    MARKET → 01,  LIMIT → 00(tick),  STOP → 스탑지정가(cndt_pric)
    BRACKET/OCO → [지정가 TP] + [스탑지정가 SL] 분해 + OCO 그룹 추적
KisBroker.reconcile_oco():  한쪽 체결 시 다른 쪽 취소 (native OCO 부재 emulation)
```

**핵심**: Option B는 복잡도를 KisBroker.submit_order/reconcile_oco로 집중시키고,
DecisionExecutor/RiskManager는 거의 건드리지 않는다. 거래소 측 스탑 보호를 얻으면서
인터페이스 호환성을 최대화. Critic #1·#3이 자연 해소됨.

## Functional Design으로 이월된 항목 (Critic + Option B)

| 항목 | 내용 | 출처 |
|---|---|---|
| ~~MARKET→LIMIT 변환~~ | ~~불필요~~ — KIS 국내주식 시장가 지원 확인, 무효화 | Critic #1 (철회) |
| **emulated OCO reconcile** | OCO 그룹 추적, 한쪽 체결 시 다른 쪽 취소 폴링 로직 | Option B 핵심 |
| 주문 유형 매핑 | MARKET→01, LIMIT→00, STOP→스탑지정가(cndt_pric) | KIS API |
| 토큰 갱신 메커니즘 | 24h 만료, 재인증 트리거 방식 | Critic HIGH #2 |
| 호가단위 반올림 | `round_to_tick()` 가격대별 (LIMIT/스탑지정가) | Critic MEDIUM #3 |
| 정수 수량 변환 | BUY/SELL floor 정책, 소액 포지션 처리 | Critic MEDIUM #6 |
| SDK import 경로 검증 | `kis_auth` vs `pykis` 실제 확인 | Critic MEDIUM #7 |
| KIS standalone 가격 피드 | steering 없이 polled exit 백업용 가격 공급 | Critic LOW |
| 잔고조회 페이징 | 모의투자 한번에 20종목 (실전 50) — 연속조회 처리 | KIS 모의투자 제약 |
