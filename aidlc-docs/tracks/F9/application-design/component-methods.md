# F9 — Component Methods (시그니처 수준)

> 비즈니스 규칙 상세는 Functional Design(per-unit)에서. 여기서는 인터페이스 계약만.

## C1. ConsoleOrderTools (TS — mcp-server.ts / steer-handler.ts)

```ts
// 각 tool은 registerTool(name, {description, inputSchema: zod}, handler).
// handler는 검증→FileDrop.send(verb,args)→문자열 결과(토큰 비노출).

place_stock_order(args: {
  symbol: string; side: "buy" | "sell";
  qty?: number; notional?: number;                 // 상호배타 (Q5/FR-7)
  order_type: "market"|"limit"|"stop"|"stop_limit"|"trailing_stop";
  time_in_force: "day"|"gtc"|"ioc"|"fok"|"opg"|"cls";  // opg/cls는 데몬서 reject (Q4=A)
  limit_price?: number; stop_price?: number;
  trail_price?: number; trail_percent?: number;
  extended_hours?: boolean; client_order_id?: string;
  order_class?: "simple"|"bracket"|"oco"|"oto";    // oto는 데몬서 reject (Q4=A)
  take_profit?: number; stop_loss?: number;
  force?: boolean;                                  // FR-5a override (Q3=A)
}): string                                          // verb="place_order"

cancel_order_by_id(args: { order_id: string }): string          // verb="cancel" (id 분기 기존)
cancel_all_orders(args: { symbol?: string }): string            // verb="cancel_all"
replace_order_by_id(args: {                                     // verb="replace_order"
  order_id: string; qty?: number; limit_price?: number;
  stop_price?: number; trail?: number; time_in_force?: string;
}): string
close_position(args: { symbol: string; qty?: number; percentage?: number }): string  // verb="close_position"
close_all_positions(args: { cancel_orders?: boolean }): string  // verb="close_all"
```
- 안전/lifecycle/approval/context 동사: 결정적 경로 유지(트림된 parser 또는 verb 직접). `force`는
  주문 tool에만.

## C2. SteeringContract (records.py ↔ schema.ts ↔ contract.json)

```python
SteeringVerb = Literal[
  # 기존 18 + 신규 주문/관리
  ..., "place_order", "replace_order", "cancel_all", "close_position", "close_all",
]
class PlaceOrderArgs(BaseModel):   # per-verb args 스키마(NFR-3) — args dict 검증용
    symbol: str; side: Literal["buy","sell"]
    qty: float | None = None; notional: float | None = None
    order_type: Literal["market","limit","stop","stop_limit","trailing_stop"]
    time_in_force: Literal["day","gtc","ioc","fok","opg","cls"] = "day"
    limit_price: float | None = None; stop_price: float | None = None
    trail_price: float | None = None; trail_percent: float | None = None
    extended_hours: bool = False; client_order_id: str | None = None
    order_class: Literal["simple","bracket","oco","oto"] = "simple"
    take_profit: float | None = None; stop_loss: float | None = None
    force: bool = False
```
- TS `schema.ts`: `ALL_VERBS`에 신규 verb 추가 + `place_order` args 미러. `contract.json` 확장 후
  계약 테스트 양쪽 green(주문 args 포함).

## C3. SteeringCommandHandler (commands.py)

```python
def _v_place_order(self, cmd) -> None      # PlaceOrderArgs 파싱→Order 초안→C5 게이트→C6 submit / reject emit
def _v_replace_order(self, cmd) -> None    # Q2=A: 단순 주문만; 대상이 bracket/oco leg면 reject emit
def _v_cancel_all(self, cmd) -> None       # broker.cancel_all_orders(symbol?)
def _v_close_position(self, cmd) -> None   # broker.close_position(symbol[, qty/percentage])
def _v_close_all(self, cmd) -> None        # broker.close_all_positions(cancel_orders?)
# 보존: _v_buy/_v_sell(결정적 shorthand→동일 게이트 합류), _v_flatten/_v_kill/_v_stop/_v_halt_* 등
```
- 공통: 시장 개장 검사·오프아워 큐잉·심볼 락·reconcile·outcome emit(토큰 비노출, FR-6 제안 포함).

## C4. OrderModel (models.py / types.py)

```python
class OrderType(str, Enum): MARKET; LIMIT; STOP; STOP_LIMIT; TRAILING_STOP   # +TRAILING_STOP
class OrderClass(str, Enum): SIMPLE; BRACKET; OCO; OTO                        # +OTO
class Order(BaseModel):
    # 기존 + 신규:
    notional: float | None = None
    extended_hours: bool = False
    client_order_id: str | None = None
    trail_price: float | None = None
    trail_percent: float | None = None
    @model_validator(mode="after")
    def _check(self) -> "Order":
        # trailing_stop → trail_price XOR trail_percent 필수
        # notional → market+day 전용 & qty와 상호배타 (FR-7)
        # bracket/oco → 양 leg 필수 (기존)
        ...
```

## C5. HumanOrderRiskGate (manager.py — 신규, evaluate_signal 무변경)

```python
class OrderDecision(BaseModel):           # 구조화 결과 (FR-6)
    accepted: bool
    order: Order | None = None
    reason_code: str = ""                 # 예: "POOL_FULL","BREAKER_HALTED","PRICE_SANITY","CLAMPED"
    message: str = ""
    suggestion: dict | None = None        # 예: {"qty": 37} 패스 가능 제안

def receive_human_order(self, order: Order, portfolio: PortfolioState,
                        price: float, *, force: bool = False) -> OrderDecision:
    # 1) order_type/price/TIF/class 존중 + 유효성(미배선 TIF/class면 reject)
    # 2) budget/pool/breaker 검사 — force=True면 우회(override 로그), price-sanity·auto-protect는 우회 불가
    # 3) qty/notional 예산 초과 → clamp 또는 reject + suggestion
    # 4) notional → 현재가로 qty 환산 후 sizer (Q5=A)
    # 5) stop/target 누락 → 자동 보호(_resolve_stop) 부착
    # 6) price-sanity 위반 → reject
# 재사용 헬퍼: _resolve_stop, position_sizer.calculate_shares, max_open_positions/_new_buys_halted 검사
```

## C6. AlpacaBrokerOrders (alpaca_broker.py / base.py)

```python
# BaseBroker 신규 추상/기본:
def replace_order(self, order_id: str, changes: dict) -> FilledOrder | None: ...   # 기본 NotImplemented/None
def cancel_all_orders(self, symbol: str | None = None) -> int: ...                 # 기본 loop 에뮬
def close_all_positions(self, cancel_orders: bool = True) -> list[FilledOrder]: ...# 기본 loop 에뮬

# AlpacaBroker:
def _build_request(self, order, side):     # +trailing_stop/notional/extended_hours 분기
def _time_in_force(self, order):           # 미지원 TIF → BrokerError(reject), 무음 DAY 강등 제거
def replace_order(...):                    # Q2=A: 단순 주문만; bracket/oco leg 대상이면 BrokerError
def cancel_all_orders(...); close_all_positions(...)  # Alpaca 네이티브 호출
```
