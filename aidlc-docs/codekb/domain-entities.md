# Domain Entities

All core entities are Pydantic v2 models / enums defined in `src/core/` and depend on nothing.

## Entity Catalog

### Bar
- **Purpose**: A single OHLCV market data bar for a symbol/timeframe.
- **Key Fields**: open/high/low/close (price), volume, timestamp, symbol, timeframe.
- **Defined In**: `src/core/models.py`

### TradeSignal
- **Purpose**: A strategy's directional output before risk sizing — the input to the RiskManager.
- **Key Fields**: symbol, side, confidence/strength, suggested levels, source strategy.
- **Relationships**: produced by `BaseStrategy` → consumed by `RiskManager`.
- **Defined In**: `src/core/models.py`

### Order / OpenOrder / FilledOrder
- **Purpose**: An intended trade (`Order`), its resting state (`OpenOrder`), and its executed state
  (`FilledOrder`). The RiskManager emits `Order`; brokers return open/filled states.
- **Key Fields**: symbol, side (`OrderSide`), type (`OrderType`), class (`OrderClass` — incl. bracket/OCO),
  quantity, limit/stop prices, status.
- **Relationships**: `RiskManager` → `Order` → `BaseBroker` → `OpenOrder`/`FilledOrder`.
- **Defined In**: `src/core/models.py`

### Position
- **Purpose**: A held position in a symbol (long/short).
- **Key Fields**: symbol, side (`PositionSide`), quantity, avg entry, market value, unrealized P/L.
- **Defined In**: `src/core/models.py`

### PortfolioState
- **Purpose**: Snapshot of the whole book — cash, positions, equity. Injected as context into agent turns.
- **Defined In**: `src/core/models.py`

### BacktestResult
- **Purpose**: Output metrics of a backtest run (returns, drawdown, trade stats).
- **Defined In**: `src/core/models.py`

### Decision (agent journal)
- **Purpose**: A machine-readable trade decision line emitted by the agent brain and consumed by the
  executor; the unit of the brain/body hand-off. Self-learning attaches `lessons_cited` + `prompt_version`.
- **Key Fields**: symbol, action, suggested levels, rationale, lessons_cited, prompt_version.
- **Defined In**: `src/agent/` (journal/decision modules) — persisted to `decisions.jsonl`.
- **Lifecycle**: appended by AgentTradingLoop → read once by DecisionExecutor (cursor-tracked) → outcome
  attributed at EOD review.

### LessonRecord (self-learning)
- **Purpose**: A single lesson learned from a trading outcome, persisted in `lessons.jsonl`. Contains recall keys (regime, sector) used by situational recall to select relevant lessons for injection into prompts.
- **Key Fields**: lesson_id, date, category, regime, sector, outcome, takeaway, signal_used.
- **Defined In**: `src/agent/journal.py`
- **Lifecycle**: Written by EOD `review.py`; recalled by `src/agent/recall.py`; efficacy tracked in `src/agent/efficacy.py`.

### SurgeRecord
- **Purpose**: Records a stock that had an abnormal EOD move (surge/dive) beyond a threshold. Used as agent analysis input during the EOD review turn.
- **Key Fields**: symbol, date, return_pct, direction (surge/dive).
- **Defined In**: `src/surge/records.py`

## Enums
- `OrderSide`, `OrderType`, `OrderClass`, `PositionSide`, `TimeFrame`, `TradingMode`, `Signal` — `src/core/types.py`.

## Exceptions
- `AutostockError` (base), `DataProviderError`, `BrokerError`, `StrategyError`, `RiskLimitError`,
  `ConfigurationError`, `InsufficientDataError` — `src/core/exceptions.py`.
