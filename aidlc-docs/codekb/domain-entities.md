# Domain Entities

## Entity Catalog

### Bar
- **Purpose**: A single OHLCV price bar for one symbol over one time period
- **Key Fields**: `timestamp: datetime`, `open: float`, `high: float`, `low: float`, `close: float`, `volume: float`
- **Relationships**: Produced by BaseDataProvider; consumed by strategies, backtest engine, risk manager (ATR calculation)
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created by data provider on fetch; immutable; held in memory or returned on-demand; not persisted directly

### TradeSignal
- **Purpose**: A strategy's recommendation for one symbol at one point in time
- **Key Fields**: `symbol: str`, `signal: Signal` (BUY/SELL/HOLD/SELL_SHORT/BUY_TO_COVER), `confidence: float [0,1]`, `sell_pct: float [0,1]`, `strategy_name: str`, `metadata: dict` (carries `key_levels` dict with entry/stop_loss/take_profit and optional `atr`)
- **Relationships**: Produced by BaseStrategy; consumed by TradingEngine which passes it to RiskManager
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Generated per-symbol per-cycle; short-lived; not persisted

### Order
- **Purpose**: A single order instruction to send to the broker
- **Key Fields**: `symbol: str`, `side: OrderSide`, `qty: float`, `order_type: OrderType`, `order_class: OrderClass` (SIMPLE/BRACKET/OCO/OTO), `take_profit_price: float | None`, `stop_loss_price: float | None`, `limit_price: float | None`, `trail_price/trail_percent` (trailing stop), `extended_hours: bool`, `client_order_id: str | None`
- **Relationships**: Created by RiskManager.validate_order(); sent to BaseBroker.place_order(); confirmed as FilledOrder
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Constructed by RiskManager; sent to broker; discarded after submission (result is FilledOrder)

### FilledOrder
- **Purpose**: Confirmation of an executed order
- **Key Fields**: `order_id: str`, `symbol: str`, `side: OrderSide`, `qty: float`, `filled_price: float`, `filled_at: datetime`, `commission: float`
- **Relationships**: Returned by BaseBroker; drives FillEvent for intraday wakes; FIFO-matched into closed round-trips
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created by broker on fill; matched into closed trades stored in workspace/trades.jsonl

### OpenOrder
- **Purpose**: A resting (open) order at the broker — protective legs or pending entries
- **Key Fields**: `order_id: str`, `symbol: str`, `side: OrderSide`, `order_type: OrderType`, `qty: float`, `limit_price: float | None`, `stop_price: float | None`
- **Relationships**: Returned by BaseBroker.get_open_orders(); used by executor for cancel/replace reconciliation on ADJUST_STOP
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Live at broker; queried for reconciliation; removed when filled or cancelled

### Position
- **Purpose**: One currently-held equity position in the portfolio
- **Key Fields**: `symbol: str`, `qty: float`, `side: PositionSide` (LONG/SHORT), `avg_entry_price: float`, `current_price: float`, `unrealized_pnl: float`, `market_value: float`
- **Relationships**: Contained in PortfolioState.positions; updated via update_price(); consumed by RiskManager (portfolio risk check), agent research prompts
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created on first fill; updated by price refreshes; removed when qty reaches 0

### PortfolioState
- **Purpose**: The complete account snapshot at a point in time
- **Key Fields**: `cash: float`, `equity: float` (authoritative from broker — single source of truth), `positions: dict[str, Position]`, `timestamp: datetime`
- **Relationships**: Returned by BaseBroker.get_portfolio_state(); injected into agent research prompts; consumed by RiskManager
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Fetched fresh from broker on each cycle; never persisted directly

### Decision
- **Purpose**: One machine-executable action written by the agent to the journal
- **Key Fields**: `ts: datetime`, `symbol: str`, `action: DecisionAction` (BUY/SELL/HOLD/ADJUST_STOP/SELL_SHORT/BUY_TO_COVER), `turn_id: str | None`, `source: Literal["agent","human"]`, `confidence: float | None`, `sell_pct: float | None`, `limit/stop/target: float | None`, `valid_until: datetime | None`
- **Relationships**: Written by AgentTradingLoop to decisions.jsonl; read by DecisionExecutor; executed as Order via RiskManager
- **Defined In**: `src/agent/journal.py`
- **Lifecycle**: Appended to decisions.jsonl; marked `executed` by executor with an outcome annotation; never deleted

### LessonRecord
- **Purpose**: A discrete trading lesson attributed to a past decision's outcome
- **Key Fields**: `lesson_id: str`, `date: str`, `category: str` (entry_timing/exit_timing/risk_mgmt/regime/thesis/sizing/other), `signal_used: str`, `outcome: str`, `takeaway: str`, `regime: str`, `sector: str | None`
- **Relationships**: Written by agent review turn to lessons.jsonl; read by recall module; efficacy tracked by LessonEfficacy (applied_n from collect_outcomes)
- **Defined In**: `src/agent/journal.py`
- **Lifecycle**: Appended at EOD review; never deleted; recalled situationally per research turn

### BacktestResult
- **Purpose**: Summary statistics for one strategy backtest run
- **Key Fields**: `strategy_name: str`, `start_date/end_date: datetime`, `initial_capital/final_capital: float`, `total_return_pct: float`, `sharpe_ratio: float`, `max_drawdown_pct: float`, `total_trades: int`, `win_rate: float`, `profit_factor: float`, `equity_curve: list[float]`, `trades: list[FilledOrder]`
- **Relationships**: Returned by BacktestEngine.run(); optionally fed into PromptAutoImprover
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Created at end of backtest run; persisted to prompt_history.json for improvement tracking

### Signal (enum)
- **Purpose**: Trading direction intent
- **Values**: `BUY`, `SELL`, `HOLD`, `SELL_SHORT`, `BUY_TO_COVER`
- **Defined In**: `src/core/types.py`

### OrderClass (enum)
- **Purpose**: Order lifecycle class for resting protective legs
- **Values**: `SIMPLE` (plain order), `BRACKET` (entry + stop + take-profit OCO), `OCO` (stop + take-profit for existing position), `OTO` (one-triggers-other, accepted but not fully wired)
- **Defined In**: `src/core/types.py`

### InterventionRecord
- **Purpose**: Audit log entry for every human steering action
- **Key Fields**: `ts: datetime`, `command_id: str`, `verb: str`, `symbol: str | None`, `outcome: str`, `source: "human"`
- **Defined In**: `src/agent/steering/records.py`
- **Lifecycle**: Written to workspace/interventions.jsonl on every handled steering command; never deleted
