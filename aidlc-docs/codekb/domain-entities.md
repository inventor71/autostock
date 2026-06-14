# Domain Entities

All core entities are Pydantic v2 models / enums defined in `src/core/` — depends on nothing.

## Entity Catalog

### Bar
- **Purpose**: A single OHLCV market data candlestick for a symbol/timeframe
- **Key Fields**: `timestamp: datetime`, `open: float`, `high: float`, `low: float`, `close: float`, `volume: int`, `symbol: str`, `timeframe: TimeFrame`
- **Relationships**: Many Bars per Symbol per TimeFrame; produced by BaseDataProvider; consumed by BaseStrategy and BacktestEngine
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Fetched from provider; TTL-cached in `IntraydayStore`; never mutated

### TradeSignal
- **Purpose**: A strategy's directional output before risk sizing — the input to RiskManager
- **Key Fields**: `symbol: str`, `signal: Signal` (BUY/SELL/HOLD), `confidence: float`, `sell_pct: float` (fraction to liquidate for SELL), `metadata: dict`
- **Relationships**: Produced by `BaseStrategy.generate_signal()`; consumed by `RiskManager`
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Generated per strategy evaluation cycle; discarded after order submission or rejection

### Order
- **Purpose**: A broker-bound trade instruction (simple, bracket, OCO, trailing stop)
- **Key Fields**: `symbol: str`, `side: OrderSide`, `qty: float`, `order_type: OrderType`, `take_profit_price: float|None`, `stop_loss_price: float|None`, `trail_price: float|None`, `trail_percent: float|None`, `extended_hours: bool`, `client_order_id: str|None`
- **Relationships**: Emitted by `RiskManager.validate_order()`; submitted to `BaseBroker`; becomes `FilledOrder`
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created → validated (RiskManager) → submitted (broker) → filled → logged in execution_log.jsonl

### OpenOrder
- **Purpose**: A resting (unexecuted) order at the broker
- **Key Fields**: `order_id: str`, `symbol: str`, `side: OrderSide`, `qty: float`, `order_type: OrderType`, `status: str`
- **Relationships**: Retrieved via `BaseBroker.get_open_orders()`; reconciled by `ReconcileWorker`
- **Defined In**: `src/core/models.py`

### FilledOrder
- **Purpose**: Confirmed execution record from the broker
- **Key Fields**: `order_id: str`, `symbol: str`, `side: OrderSide`, `qty: float`, `filled_price: float`, `filled_at: datetime`, `commission: float`
- **Relationships**: Aggregated into round-trip trades; persisted to `trades_log.jsonl`
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created on broker fill event; persisted; consumed by quality metrics

### Position
- **Purpose**: Current open exposure in a single symbol (long or short)
- **Key Fields**: `symbol: str`, `side: PositionSide` (LONG/SHORT), `qty: float`, `entry_price: float`, `current_price: float`, `unrealized_pnl: float`
- **Relationships**: Many Positions per PortfolioState; queried by RiskManager before every order
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created on first fill; updated on price tick; closed on full liquidation

### PortfolioState
- **Purpose**: Snapshot of the full account at a point in time
- **Key Fields**: `cash: float`, `equity: float`, `buying_power: float`, `positions: dict[str, Position]`
- **Relationships**: Contains many Positions; injected as context into agent turns; queried by RiskManager
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Fetched from broker on demand; not cached (always live in agent mode)

### BacktestResult
- **Purpose**: Aggregated performance report for one backtest run
- **Key Fields**: `strategy_name: str`, `total_return_pct: float`, `sharpe_ratio: float`, `max_drawdown_pct: float`, `total_trades: int`, `win_rate: float`, `profit_factor: float`, `final_capital: float`
- **Relationships**: Produced by BacktestEngine; optionally fed to LLM auto-improver
- **Defined In**: `src/core/models.py`

### Decision (Agent Journal)
- **Purpose**: A machine-readable trade decision emitted by the agent brain; the unit of brain/body hand-off
- **Key Fields**: `symbol: str`, `action: DecisionAction`, `qty: float`, `ts: datetime`, `rationale: str`, `lessons_cited: list[str]`, `prompt_version: str`, `source: Literal["agent", "human"]`, `turn_id: str|None`, `limit: float|None`, `stop: float|None`, `target: float|None`, `valid_until: datetime|None`
- **Relationships**: Many Decisions per Journal; each Decision has 0-1 FilledOrder; cursor tracks last executed index
- **Defined In**: `src/agent/journal.py` — persisted to `decisions.jsonl`
- **Lifecycle**: Appended by `AgentTradingLoop`; consumed once by `DecisionExecutor` (cursor-tracked); outcome attributed at EOD self-review

### Thesis (Agent)
- **Purpose**: LLM conviction statement for a position — entry rationale plus bracket levels
- **Key Fields**: `symbol: str`, `rationale: str`, `entry_price: float`, `stop_loss: float`, `take_profit: float`, `conviction: float`
- **Relationships**: Associated with a Decision; informs bracket Order construction
- **Defined In**: `src/agent/journal.py`

### LessonRecord (Self-Learning)
- **Purpose**: A single lesson learned from a trading outcome; persisted for situational recall
- **Key Fields**: `lesson_id: str`, `date: str`, `category: str`, `regime: str`, `sector: str`, `outcome: str`, `takeaway: str`, `signal_used: str`
- **Relationships**: Written by EOD `review.py`; recalled by `src/agent/learning/recall.py`; efficacy tracked by `src/agent/learning/efficacy.py`
- **Defined In**: `src/agent/journal.py` — persisted to `lessons.jsonl`
- **Lifecycle**: Written at EOD; recalled by regime/sector match; attribution tracks `lessons_cited` on Decision

### SurgeRecord
- **Purpose**: Records a stock with an abnormal EOD move (surge/dive) beyond a threshold
- **Key Fields**: `symbol: str`, `date: str`, `return_pct: float`, `direction: str` (surge/dive)
- **Relationships**: Written by `SurgeDetector`; consumed by agent EOD review turn
- **Defined In**: `src/surge/records.py`

### IpoRow (Signals — F78)
- **Purpose**: Raw IPO listing row fetched from the Finnhub IPO calendar
- **Key Fields**: `name: str`, `symbol: str|None`, `ipo_date: date`, `exchange: str|None`, `status: Literal["expected","priced","withdrawn","filed"]`, `est_value: float|None`, `price_low: float|None`, `price_high: float|None`, `shares: int|None`
- **Relationships**: Raw input to `select_imminent_ipos()` → `ImminentIpo`
- **Defined In**: `src/signals/records.py`
- **Lifecycle**: Fetched from Finnhub `/calendar/ipo`; withdrawn rows dropped immediately

### ImminentIpo (Signals — F78)
- **Purpose**: A filtered, size-ranked imminent IPO surfaced in the research brief
- **Key Fields**: `name: str`, `symbol: str|None`, `ipo_date: date`, `exchange: str|None`, `status: str`, `est_value: float|None`, `in_universe: bool`, `is_held: bool`
- **Relationships**: Produced by `select_imminent_ipos()` from `IpoRow` list; injected into `SignalBrief` for agent research prompt; also exposed via the `ipo_calendar` agent tool
- **Defined In**: `src/signals/records.py`
- **Lifecycle**: Assembled per research turn; NOT universe-filtered (IPOs are awareness-only); ranked by `est_value` desc, capped at `max_ipos`; `in_universe`/`is_held` are tags, not filters

### CommandRecord (Steering)
- **Purpose**: A human operator command received via file-drop channel
- **Key Fields**: `verb: str` (lock/approve/place/adjust), `args: dict`, `requester: str`, `status: str`, `reason: str`
- **Relationships**: Processed by SteeringRuntime → CommandBus → RiskManager → Broker
- **Defined In**: `src/agent/steering/records.py`

### ApprovalRecord (Steering)
- **Purpose**: Human approval or rejection of a specific LLM decision
- **Key Fields**: `decision_id: str`, `approved_by: str`, `requested_by: str`, `reason: str`
- **Relationships**: Gates DecisionExecutor — decision's order is only submitted after approval
- **Defined In**: `src/agent/steering/records.py`

## Enums (`src/core/types.py`)

- `Signal`: BUY / SELL / HOLD / SELL_SHORT / BUY_TO_COVER (F54: short-selling signals added)
- `OrderSide`: buy / sell / sell_short / buy_to_cover (F54: maps 1:1 to Alpaca's native short sides)
- `OrderType`: MARKET / LIMIT / STOP / STOP_LIMIT / TRAILING_STOP (F9: trailing stop via trail_price or trail_percent)
- `OrderClass`: SIMPLE / BRACKET / OCO / OTO
- `PositionSide`: LONG / SHORT
- `TimeFrame`: MINUTE_1(1m) / MINUTE_5(5m) / MINUTE_15(15m) / MINUTE_30(30m) / HOUR_1(1h) / HOUR_4(4h) / DAY_1(1d) / WEEK_1(1w) / MONTH_1(1mo)
- `TradingMode`: backtest / paper / live / agent

## DecisionAction (`src/agent/journal.py`)

Literal type used for agent journal entries: `BUY` / `SELL` / `HOLD` / `ADJUST_STOP` / `SELL_SHORT` / `BUY_TO_COVER`

## Exceptions (`src/core/exceptions.py`)

- `AutostockError` (base), `DataProviderError`, `BrokerError`, `StrategyError`, `RiskLimitError`, `ConfigurationError`, `InsufficientDataError`
