# F30 Application Design — Consolidated

> KIS OpenAPI 브로커 확장을 위한 애플리케이션 설계

## 1. Component Inventory

| # | Component | File | Type |
|---|---|---|---|
| 1 | `KisBroker` | `src/execution/brokers/kis_broker.py` | NEW |
| 2 | `KisDataProvider` | `src/data/providers/kis_provider.py` | NEW |
| 3 | `DecisionExecutor` | `src/agent/executor.py` | MODIFY (1곳: 서킷브레이커 broker-aware) |
| 4 | `TradingScheduler` | `src/trading/scheduler.py` | MODIFY (KST 파라미터) |
| 5 | `AgentTradingMode` | `src/trading/modes/agent.py` | MODIFY (KIS 브로커 + KST wiring) |
| 6 | `BaseBroker` | `src/execution/base.py` | MODIFY (halt_reference_symbol 1개) |

## 2. Architecture

```
autostock (F30 KIS standalone)
    │
    ├── KisBroker (NEW) — 복잡도 집중
    │   ├── implements BaseBroker ABC
    │   ├── 시장가(01)/지정가(00)/스탑지정가(cndt_pric) 매핑
    │   ├── emulated bracket/OCO: 스탑지정가 SL + 지정가 TP resting + reconcile_oco()
    │   ├── 토큰 24h 갱신, round_to_tick, 정수 수량
    │   ├── wraps KIS SDK
    │   └── targets KOSPI/KOSDAQ
    │
    ├── KisDataProvider (NEW)
    │   ├── implements BaseDataProvider ABC
    │   └── wraps KIS SDK for market data
    │
    ├── BaseBroker (MODIFIED)
    │   └── + halt_reference_symbol: str = "SPY"   (KIS="069500")
    │
    ├── DecisionExecutor (MODIFIED: 1곳)
    │   └── _update_market_halt(): broker.halt_reference_symbol 참조
    │       (bracket 검증·_place_protection은 변경 없음 — KisBroker가 emulate)
    │
    ├── TradingScheduler (MODIFIED)
    │   └── add_market_open/close(): timezone/hour/minute params
    │
    └── AgentTradingMode (MODIFIED)
        └── KIS broker + KST scheduler wiring
```

## 3. Key Design Decisions

| Decision | Rationale |
|---|---|
| **emulated bracket/OCO (Option B)** | KIS 스탑지정가 resting order로 거래소 측 보호; OCO 자동취소는 reconcile 폴링 |
| 복잡도 KisBroker 집중 | DecisionExecutor/RiskManager 거의 무변경 → Critic #1·#3 자연 해소 |
| 서킷브레이커 broker-aware | `halt_reference_symbol` — KIS는 KODEX 200(069500) 참조 (Critic MEDIUM #4) |
| ~~RiskManager broker-aware~~ | ~~MARKET→LIMIT 변환~~ — 철회: KIS 국내주식 시장가(ORD_DVSN=01) 정상 지원 |
| KisBroker wraps KIS SDK | 기존 AlpacaBroker 패턴 준수, 공식 SDK 활용 |
| TradingScheduler 파라미터화 | 하위 호환 유지하며 KST 지원 |
| 보호 defense-in-depth | ① 거래소 스탑지정가(주) ② polled exit(백업) |
| 토큰 24h 자동 갱신 | KIS 토큰 만료 대응 (Critic HIGH #2) |
| 호가단위 round_to_tick | KOSPI/KOSDAQ tick 단위 (Critic MEDIUM #3) |
| Single-broker scope (F30) | 멀티브로커는 F33에서 별도 설계 |

## 4. Dependency Graph

```
pyproject.toml (+ open-trading-api)
         │
    ┌────┴────┐
    │         │
KisBroker  KisDataProvider
    │         │
    ├── src/execution/base.py
    ├── src/core/models.py
    ├── src/execution/brokers/session_timeout.py
    │
    ├── src/data/base.py
    ├── src/core/types.py
    
DecisionExecutor ──→ BaseBroker.supports_bracket_orders
TradingScheduler  ──→ add_market_open_job(tz, h, m)
AgentTradingMode  ──→ KisBroker + KST scheduler
```

## 5. Artifacts

| Artifact | File |
|---|---|
| Components | `components.md` |
| Component Methods | `component-methods.md` |
| Services & Orchestration | `services.md` |
| Dependencies & Data Flow | `component-dependency.md` |
