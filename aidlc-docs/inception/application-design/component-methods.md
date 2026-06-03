# F30 Application Design — Component Methods

## KisBroker Method Signatures

> 참조: `src/execution/base.py` — BaseBroker ABC
> KIS-specific 변환 규칙은 Functional Design에서 상세 정의

### Constructor
```python
class KisBroker(BaseBroker):
    supports_bracket_orders: bool = False  # capability 선언
    supports_market_orders: bool = False

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
        rate_limit_per_sec: float = 15.0,
    ):
        """
        KIS SDK 초기화 + 인증.
        paper=True → auth(svr="vps")
        paper=False → auth(svr="prod")
        install_session_timeout으로 HTTP 타임아웃 적용.
        """
```

### Core ABC Methods
```python
def submit_order(self, order: Order) -> FilledOrder:
    """
    KIS 국내주식 주문 API 호출.
    Order → KIS 주문 파라미터 변환 (Functional Design).
    주문번호 추출, polling/direct fill 확인.
    """

def get_position(self, symbol: str) -> Position | None:
    """
    KIS 잔고조회 API → 단일 종목 Position.
    심볼 매핑: autostock symbol → KIS pdno.
    """

def get_all_positions(self) -> list[Position]:
    """
    KIS 잔고조회 API → 전체 Position 리스트.
    연속조회(페이징) 처리 포함.
    """

def get_portfolio_state(self) -> PortfolioState:
    """
    KIS 잔고조회 + 예수금 API → PortfolioState.
    cash = 예수금 + 위탁증거금 여유분
    equity = 총평가금액
    positions = get_all_positions() 결과
    """

def cancel_order(self, order_id: str) -> bool:
    """
    KIS 주문취소 API 호출.
    원주문번호(odno)로 취소.
    """

def close_position(self, symbol: str) -> FilledOrder | None:
    """
    보유 수량 확인 → KIS 현재가 조회 → 지정가 매도 주문.
    가격 전략: 현재가 bid 기준 (Functional Design에서 상세).
    """

def get_order_status(self, order_id: str) -> FilledOrder | None:
    """
    KIS 주문내역조회 API → 체결 상태 확인.
    미체결이면 filled_qty=0, filled_price=0.
    """
```

### Optional Methods
```python
def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
    """
    KIS 미체결주문조회 API.
    미체결 상태인 주문만 필터링.
    """

def is_market_open(self) -> bool:
    """
    KST 기준 장 시간 확인: 09:00-15:30, Mon-Fri.
    KIS 시장시간 API 또는 datetime 계산.
    Fail-closed: 오류 시 False 반환.
    """

def get_fills(self, since: str | None = None) -> list[FillEvent]:
    """
    KIS 체결내역 API → FillEvent 리스트.
    since = transaction_time 커서 (idempotent).
    """

def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
    """
    KIS 실시간 시세 API → 현재가.
    Batch 조회 최적화 (단일 API 호출).
    """

def record_trade_ledger(self, path: str | Path, *, since=None, min_notional=0.0):
    """
    KIS 체결내역 기반 round-trip 재구성.
    """

def replace_order(self, order_id: str, changes: dict) -> FilledOrder | None:
    """
    KIS 주문정정 API (가능한 경우).
    정정 불가 주문이면 None 반환.
    """
```

---

## KisDataProvider Method Signatures

> 참조: `src/data/base.py` — BaseDataProvider ABC

### Constructor
```python
class KisDataProvider(BaseDataProvider):
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        http_connect_timeout: float = 3.0,
        http_read_timeout: float = 5.0,
    ):
        """
        KIS SDK or 직접 REST client 초기화.
        paper=True → demo API endpoint.
        """
```

### Core ABC Methods
```python
def get_bars(
    self,
    symbol: str,
    timeframe: TimeFrame = TimeFrame.DAY_1,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> pd.DataFrame:
    """
    KIS 국내주식 일봉/분봉 시세 API → OHLCV DataFrame.
    timeframe → KIS tr_id 매핑 (분/일).
    Columns: open, high, low, close, volume
    Index: DatetimeIndex
    """

def get_latest_price(self, symbol: str) -> float:
    """
    KIS 실시간 시세 API → 현재가.
    """
```

---

## Modified Method Signatures

### BaseBroker (NEW attribute) — Option B 반영
```python
class BaseBroker(ABC):
    halt_reference_symbol: str = "SPY"     # NEW: circuit-breaker benchmark (KIS→KOSPI index)
```
- `AlpacaBroker` / `SimulatedBroker`: 기본값 `"SPY"` — 변경 없음
- `KisBroker`: `halt_reference_symbol="069500"` (KODEX 200 ETF)

> **정정 (2026-06-02) — Option B 결정**:
> - `supports_market_orders` 플래그 **불필요**: KIS 국내주식 시장가(ORD_DVSN=01) 정상 지원.
> - `supports_bracket_orders` 플래그도 **불필요**: KIS는 단일 스탑지정가 주문(cndt_pric)을
>   exchange resting order로 지원 → KisBroker가 OCO/BRACKET을 **emulate**(스탑지정가 SL +
>   지정가 TP 개별 resting order + 폴링 reconcile). DecisionExecutor 입장에서는 모든 브로커가
>   bracket 지원처럼 보이고 `use_bracket_orders=True`로 동작 → Critic #1·#3 **자연 해소**.
> - 결과: BaseBroker 신규 속성은 `halt_reference_symbol` **1개만**.

### KisBroker.submit_order — emulated bracket/OCO (Option B 핵심)
```python
def submit_order(self, order: Order) -> FilledOrder:
    """
    order_class / order_type별 처리:
    - MARKET → KIS ORD_DVSN=01 (시장가)
    - LIMIT  → KIS ORD_DVSN=00 (지정가, 호가단위 반올림)
    - STOP   → KIS 스탑지정가(cndt_pric=stop_price) resting order
    - BRACKET(진입+TP+SL) → 진입 체결 후 [지정가 TP]+[스탑지정가 SL] 2개 resting order, OCO 그룹 추적
    - OCO(TP+SL) → [지정가 TP]+[스탑지정가 SL] 2개 resting order, OCO 그룹 추적
    KIS는 네이티브 OCO 자동취소가 없으므로 한쪽 체결 시 다른 쪽 취소를 폴링으로 emulate.
    """

def reconcile_oco(self) -> None:
    """OCO 그룹의 한쪽 leg 체결 시 다른 쪽 취소 (native OCO 부재 emulation).
    get_open_orders + get_position 비교. SimulatedBroker의 OCO group semantics를
    거래소 폴링 버전으로 재현. (Functional Design에서 상세)"""
```

### RiskManager (변경 없음 — 정정됨)
KIS 국내주식이 시장가를 지원하므로 RiskManager의 MARKET 주문이 그대로 동작한다.
broker-aware MARKET→LIMIT 변환 로직 **제거** (Critic #1 무효화). KisBroker가 주문 유형 매핑 흡수.

### DecisionExecutor (변경 최소화 — Option B로 단순해짐)
```python
# Critic #1(bracket reject) 무효: KIS도 use_bracket_orders=True로 동작 → 기존 __init__ 검증 통과.
# Critic #3(_place_protection OCO/STOP) 무효: KisBroker가 OCO/STOP emulate → 그대로 동작.
# 유일한 변경: 서킷브레이커 broker-aware (Critic MEDIUM #4)
def _update_market_halt(self) -> None:
    ref = getattr(self.broker, "halt_reference_symbol", "SPY")
    bars = self.data_provider.get_bars(ref, limit=2)   # KIS: "069500"(KODEX 200)
```

### TradingScheduler (MODIFIED)
```python
def add_market_open_job(
    self, func, job_id: str = "market_open",
    timezone: str = "US/Eastern",  # NEW
    hour: int = 9,                 # NEW
    minute: int = 30,              # NEW
) -> None:
    """Run at market open. Defaults to US Eastern 9:30 AM."""

def add_market_close_job(
    self, func, job_id: str = "market_close",
    timezone: str = "US/Eastern",  # NEW
    hour: int = 15,                # NEW
    minute: int = 55,              # NEW
) -> None:
    """Run near market close. Defaults to US Eastern 3:55 PM."""
```

### DecisionExecutor.__init__ — 변경 불필요 (Option B)
KIS도 `use_bracket_orders=True`로 RiskManager를 구성하므로 `executor.py:58-62`의 기존
`if not risk_manager.use_bracket_orders: raise ValueError` 검증을 그대로 통과한다.
KisBroker가 OCO/BRACKET을 emulate하므로 `_place_protection`/`_adjust_stop`도 변경 없이 동작.
→ Critic #1(bracket reject)·#3(OCO/STOP 생성) 모두 무효.
