# F30 Application Design — Services

## Service Layer

F30은 기존 서비스 계층을 유지하며, 브로커/데이터 제공자만 교체 가능하게 한다. 새 서비스는 필요하지 않다.

### Existing Service Integration

```
AgentTradingMode (agent mode)
    │
    ├── AgentTradingLoop → claude CLI (agent brain)
    │       │
    │       └── DecisionExecutor ──→ RiskManager ──→ Broker
    │           (KIS: bracket no-op)    │              │
    │                                   │    ┌─────────┴──────────┐
    │                                   │    │                    │
    │                                   │  AlpacaBroker       KisBroker
    │                                   │  (US stocks)        (KR stocks)
    │                                   │  bracket=True       bracket=False
    │                                   │                    (F30 scope:
    │                                   │                     single broker)
    │
    ├── TradingScheduler (APScheduler)
    │       ├── add_market_open_job   (KST now supported)
    │       ├── add_market_close_job  (KST now supported)
    │       └── add_daily_job         (already timezone-aware)
    │
    └── IntradaySnapshotPublisher → broker.get_fills()
                                   → broker.get_latest_prices()
```

### F30 Service Naming Convention

| 기존 (US) | F30 KIS (KR) | 설명 |
|---|---|---|
| `autostock run --mode agent --broker alpaca` | `autostock run --mode agent --broker kis` | 브로커 선택 |
| `AlpacaBroker(paper=True)` | `KisBroker(paper=True)` | 모의투자 |
| TradingScheduler US/Eastern | TradingScheduler Asia/Seoul | 타임존 |

### Orchestration Flow (KIS standalone)

```
1. AgentTradingMode.start()
     ├── broker = KisBroker(paper=True)
     ├── data_provider = KisDataProvider(paper=True)
     ├── risk_manager = RiskManager(use_bracket_orders=False)
     ├── executor = DecisionExecutor(broker, risk_manager, data_provider)
     │       └── _broker_supports_bracket = False → KIS path
     │
     └── scheduler:
           ├── add_daily_job(research, hour=8, tz="Asia/Seoul")    # 08:00 KST 리서치
           ├── add_market_open_job(execute, hour=9, minute=0, tz="Asia/Seoul")  # 09:00 KST 개장
           ├── add_market_close_job(eod, hour=15, minute=20, tz="Asia/Seoul")    # 15:20 KST 마감 전
           └── add_seconds_job(snapshot, 5, "intraday_snapshot")

2. 연구 턴 (08:00 KST):
     AgentTradingLoop.research()
     → 한국 주식 뉴스/시세 분석
     → decisions.jsonl 생성

3. 개장 실행 (09:00 KST) — Option B:
     DecisionExecutor.execute_pending()
     → 새 decisions.jsonl 라인 읽기
     → BUY (levels 포함) → RiskManager (use_bracket_orders=True)
       → Order(order_class=BRACKET, tp, sl) → KisBroker.submit_order()
       → KisBroker: 진입(시장가/지정가) 체결 후 [지정가 TP]+[스탑지정가 SL] resting order, OCO 그룹 등록
     → HOLD/ADJUST_STOP → _place_protection/_adjust_stop → KisBroker가 OCO emulate (변경 없음)
     → 보호: ① 거래소 resting 스탑지정가(주) ② run_polled_exits() 폴링(백업)

4. Intraday (5초 간격):
     KisBroker.reconcile_oco(): OCO 그룹 한쪽 체결 시 다른 쪽 취소 (native OCO 부재 emulation)
     ※ Critic LOW: add_seconds_job(snapshot, ...)은 agent.py:313-345에서 `if self.steering`
       블록 안 → steering 없이 KIS 단독 실행 시 가격 피드 부재.
     → KIS standalone에서 steering 무관하게 동작하는 최소 가격 리프레시 + reconcile_oco job 등록
       (Code Gen에서 처리). 거래소 스탑이 1차 보호이므로 가격피드 부재 시에도 보호는 유지.
     IntradaySnapshotPublisher.publish() (steering 있을 때)
     → broker.get_fills(since) / broker.get_latest_prices(universe) → 콘솔 업데이트

5. EOD (15:20 KST):
     AgentTradingLoop.eod()
     → broker.record_trade_ledger()
     → quality metrics
     → self-review
```
