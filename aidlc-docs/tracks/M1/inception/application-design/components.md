# F30 Application Design — Components

## Component Overview

```
                    autostock (F30)
                         |
        +----------------+----------------+
        |                |                |
   KisBroker       KisDataProvider    Modified Components
   (NEW)           (NEW)              (executor/scheduler/mode)
        |                |
   BaseBroker ABC   BaseDataProvider ABC
```

---

## Component 1: KisBroker

**File**: `src/execution/brokers/kis_broker.py`

### Purpose
한국투자증권 OpenAPI를 통해 한국주식(KOSPI/KOSDAQ) 거래를 수행하는 브로커 어댑터. BaseBroker ABC를 구현하며, KIS SDK를 래핑한다.

### Responsibilities
- KIS SDK 초기화 및 인증 관리 (실제 import 경로는 Code Gen 전 검증 — Critic: `kis_auth`/`pykis` 미확정)
- **토큰 수명 관리 (Critic HIGH #2)**: KIS 액세스 토큰 24시간 만료 → 자동 재인증
  (매 API 호출 전 토큰 나이 체크 후 >23h이면 재발급, 또는 23h 주기 백그라운드 갱신)
- 국내주식 주문 제출 (시장가 01 / 지정가 00 / 스탑지정가 cndt_pric)
- **emulated bracket/OCO (Option B)**: BRACKET/OCO order_class를 단일 resting order들로 분해,
  OCO 그룹 추적 + `reconcile_oco()` 폴링으로 한쪽 체결 시 다른 쪽 취소
- **호가단위 반올림 (Critic MEDIUM #3)**: 모든 LIMIT/스탑지정가 가격을 KOSPI/KOSDAQ tick 단위로 반올림
  (`round_to_tick(price)` — 가격대별 1/5/10/50/100/500/1000원)
- 포지션/잔고/포트폴리오 상태 조회 (모의투자 잔고조회 20종목/회 페이징)
- 주문 취소 및 상태 추적
- Paper/Live 환경 전환
- KIS API rate limit 준수 (초당 20회, 모의는 더 낮음)
- HTTP 타임아웃 적용 (F14 패턴)

### Interface (BaseBroker ABC 구현)
```
submit_order(order) → FilledOrder
get_position(symbol) → Position | None
get_all_positions() → list[Position]
get_portfolio_state() → PortfolioState
cancel_order(order_id) → bool
close_position(symbol) → FilledOrder | None
get_order_status(order_id) → FilledOrder | None

+ override:
get_open_orders(symbol) → list[OpenOrder]
is_market_open() → bool       (KST 09:00-15:30, Mon-Fri)
get_fills(since) → list[FillEvent]
get_latest_prices(symbols) → dict[str, float]
record_trade_ledger(path, ...) → None
replace_order(order_id, changes) → FilledOrder | None
cancel_all_orders(symbol) → int
close_all_positions(cancel_orders) → list[FilledOrder]
```

### Capability (Option B)
- **시장가 주문**: ✅ 국내주식 ORD_DVSN=01 (모의투자 포함)
- **스탑지정가 주문**: ✅ 단일 resting stop-limit (cndt_pric) — exchange-side 보호 가능
- **bracket/OCO**: 네이티브 없음 → **KisBroker가 emulate** (스탑지정가 SL + 지정가 TP 개별 resting
  order, OCO 자동취소는 `reconcile_oco()` 폴링으로 재현). DecisionExecutor엔 bracket 지원처럼 보임.
- **halt_reference_symbol**: `"069500"` (KODEX 200 ETF) — 서킷브레이커 한국 지수 참조 (Critic MEDIUM #4)
- **price_unit**: KRW 정수, 지정가/스탑지정가 주문 시 호가단위 반올림 적용
- **qty_unit**: 정수 (소수점 주식 불가) — BUY floor, SELL floor (Functional Design에서 정책 확정)
- **보호 계층 (defense-in-depth)**: ① exchange resting stop-limit(주) ② polled exit(백업)

### Dependencies
- `kis_auth` (from open-trading-api SDK)
- `src/execution/base.py` (BaseBroker ABC)
- `src/core/models.py` (Order, Position, PortfolioState, FilledOrder, OpenOrder, FillEvent)
- `src/execution/brokers/session_timeout.py` (install_session_timeout)

---

## Component 2: KisDataProvider

**File**: `src/data/providers/kis_provider.py`

### Purpose
KIS OpenAPI를 통해 한국주식 시세 데이터(일봉/분봉 OHLCV, 실시간 가격)를 제공하는 데이터 제공자. BaseDataProvider ABC를 구현한다.

### Responsibilities
- KIS SDK를 통한 OHLCV 바 조회 (일봉/분봉)
- 실시간 가격 조회
- KIS 시세 데이터 → autostock DataFrame 포맷 변환
- Rate limit 준수 (시세 API 호출 제한)

### Interface (BaseDataProvider ABC 구현)
```
get_bars(symbol, timeframe, start, end, limit) → pd.DataFrame
get_latest_price(symbol) → float
get_multiple_bars(symbols, ...) → dict[str, pd.DataFrame]  (inherited)
```

### Dependencies
- `kis_auth` (from open-trading-api SDK)
- `src/data/base.py` (BaseDataProvider ABC)
- `src/core/types.py` (TimeFrame enum)

---

## Component 3: DecisionExecutor (MODIFIED — 1곳만, Option B로 단순화)

**File**: `src/agent/executor.py`

### 유일한 변경: 서킷브레이커 broker-aware (executor.py:292-300, Critic MEDIUM #4)
```python
# 기존: get_bars("SPY", ...) 하드코딩
# 변경: broker.halt_reference_symbol 사용 (KIS → KODEX 200)
ref = getattr(self.broker, "halt_reference_symbol", "SPY")
bars = self.data_provider.get_bars(ref, limit=2)
```

### 변경 불필요해진 것 (Option B로 자연 해소)
- **bracket 검증 (executor.py:58-62)**: KIS도 `use_bracket_orders=True`로 동작 → 기존 검증 통과
- **_place_protection / _adjust_stop**: OCO/STOP 주문을 KisBroker가 emulate → 그대로 동작
- `execute_decision()`/HOLD/ADJUST_STOP 모두 기존 Alpaca 경로와 동일하게 작동
- 거래소 측 스탑 보호(KisBroker resting order) + polled exit 백업 (defense-in-depth)

## Component 6: RiskManager (변경 없음 — 정정됨)

**File**: `src/risk/manager.py`

> **정정 (2026-06-02)**: 당초 KIS 시장가 미지원으로 오판하여 broker-aware MARKET→LIMIT 변환을
> 계획했으나, KIS **국내주식**은 시장가(ORD_DVSN=01)를 모의투자 포함 정상 지원함을 확인.
> RiskManager의 MARKET 주문이 그대로 동작하므로 **변경 불필요**. KisBroker가 MARKET → ORD_DVSN=01 매핑.

---

## Component 4: TradingScheduler (MODIFIED)

**File**: `src/trading/scheduler.py`

### Change
시장 시간을 파라미터화:

```python
# 기존
def add_market_open_job(self, func, job_id="market_open"):
    # hour=9, minute=30, timezone="US/Eastern" 하드코딩

# 변경
def add_market_open_job(self, func, job_id="market_open",
                         timezone="US/Eastern", hour=9, minute=30):
    # 하위 호환 유지
```

KIS 사용:
```python
scheduler.add_market_open_job(on_open, "kr_market_open",
                               timezone="Asia/Seoul", hour=9, minute=0)
scheduler.add_market_close_job(on_close, "kr_market_close",
                               timezone="Asia/Seoul", hour=15, minute=30)
```

---

## Component 5: AgentTradingMode (MODIFIED)

**File**: `src/trading/modes/agent.py`

### Change
KIS 브로커/스케줄러 주입 + KST 연구 스케줄:

- `_resolve_research_schedule()`: `market_open_min`을 `broker`에서 가져오거나 파라미터화
- `start()`: KIS 브로커 선택 시 KST 기반 스케줄 등록
- `_intraday()`: `broker.is_market_open()` 체크 (이미 존재하므로 override만 필요)
