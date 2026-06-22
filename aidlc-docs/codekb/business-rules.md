# Business Rules

## Rules by Domain

### Order Safety

#### Brain / Body Split (Hard)
- **Rule**: The LLM agent writes decisions to decisions.jsonl but NEVER calls any broker method directly. The deterministic DecisionExecutor is the sole actuator.
- **Rationale**: A model is a brilliant analyst and a terrible fiduciary — it proposes, it cannot act.
- **Implemented In**: `src/agent/orchestrator.py`, `src/agent/executor.py`; AgentTradingLoop holds no broker reference
- **Invariants**: No broker import in orchestrator.py; only executor holds the broker reference

#### Single Risk Gate (Hard)
- **Rule**: Every order — from agent, strategy engine, or human steering — must pass through `RiskManager.validate_order()` before any broker call. No code path bypasses this.
- **Rationale**: One gate for position sizing, circuit breaker, bracket leg validation, and short safety — inconsistencies impossible when there is only one path.
- **Implemented In**: `src/risk/manager.py:RiskManager.validate_order()`; enforced at every call site in executor, commands.py, TradingEngine
- **Invariants**: No `BaseBroker.place_order()` call exists outside a path that went through RiskManager

#### Idempotent Execution (Hard)
- **Rule**: The executor uses an append-only cursor on decisions.jsonl. A Decision is executed at most once regardless of crashes and restarts.
- **Rationale**: The hand-off is an append-only file; crash-and-restart must never double-submit an order.
- **Implemented In**: `src/agent/executor.py` (cursor tracking), `src/agent/journal.py` (append-only writes)
- **Invariants**: turn_id dedup prevents re-execution of decisions from the same agent turn

### Risk Management

#### Position Size is Risk-Budget Driven
- **Rule**: Position size = (equity * max_portfolio_risk) / stop_distance_$. Risk is always capped at max_portfolio_risk per trade.
- **Rationale**: Ensures per-trade dollar risk is constant regardless of stop width; prevents a wide stop from creating an oversized position.
- **Implemented In**: `src/risk/position_sizer.py:PositionSizer`
- **Invariants**: Position size is always <= max_position_pct * equity

#### Resting Bracket Orders (Hard — agent path)
- **Rule**: Agent BUY orders include exchange-resting stop-loss and take-profit as an OCO pair (BRACKET order). The exchange triggers them — no polling loop.
- **Rationale**: Polling-based stops miss gap moves; exchange-held stops are gap-safe. OCO guarantees only one leg fills.
- **Implemented In**: `src/risk/manager.py` (bracket construction), `src/core/models.py:Order._check_bracket_legs()` (validation)
- **Invariants**: BRACKET/OCO orders always carry both take_profit_price and stop_loss_price; geometry validated (long: stop < entry < target; short: target < entry < stop)

#### Circuit Breaker
- **Rule**: When SPY daily change falls to <= market_halt_threshold_pct (-3% default), new buy entries are halted. New short entries are halted when SPY rises >= short_market_halt_threshold_pct (+3%).
- **Rationale**: Prevent digging deeper in a market-wide move; let the human reassess.
- **Implemented In**: `src/risk/manager.py:RiskManager._check_market_halt()`
- **Invariants**: BUY_TO_COVER (covering an existing short) and SELL (exiting a long) are never halted; only new entries

#### Max Open Positions Cap
- **Rule**: New entries are rejected once len(positions) >= max_open_positions (default 20).
- **Implemented In**: `src/risk/manager.py`
- **Invariants**: Exits are always allowed regardless of position count

### Short Selling

#### Shorting Off by Default (Hard)
- **Rule**: `risk.shorting_enabled: false` by default. All short entries (SELL_SHORT from agent, /short console command) are rejected when disabled.
- **Rationale**: Short selling carries unlimited downside; must be an explicit per-deployment opt-in.
- **Implemented In**: `src/risk/manager.py:RiskManager.validate_order()` (short master guard)
- **Invariants**: BUY_TO_COVER remains allowed even when shorting_enabled=false — exit of an existing short must always be possible

#### Short Mandatory Stop (Hard)
- **Rule**: A SELL_SHORT order without a stop-loss level is always rejected. Shorts must always carry a protective stop.
- **Rationale**: Without a stop, a short's loss is unbounded.
- **Implemented In**: `src/risk/manager.py` (short bracket guard); `src/agent/steering/commands.py:build_human_short()` (returns None when no stop can be resolved)
- **Invariants**: No code path places an uncovered short without a stop

#### Short Individual Stock Halt
- **Rule**: A fresh short entry is rejected if the target name's intraday price change is >= individual_stock_halt_pct (+10% default).
- **Rationale**: Shorting into a momentum surge risks a squeeze.
- **Implemented In**: `src/risk/manager.py`

#### Short ETB Gate
- **Rule**: A short entry requires BaseBroker.is_shortable() to return True. Defaults False on unknown status (fail-closed).
- **Rationale**: Borrow cost and forced-recall risk on hard-to-borrow names.
- **Implemented In**: `src/execution/base.py:BaseBroker.is_shortable()`, `src/execution/brokers/alpaca_broker.py`

### Agent Self-Improvement

#### Constitution-Bounded Self-Rewrite
- **Rule**: The agent's guidance prompt is self-writable, but the AGENT_CONSTITUTION prepended block is immutable. A compliance check gates every rewrite. The constitution's SHA-256 is pinned in CI.
- **Rationale**: Allow adaptive learning without allowing the agent to remove its own safety or quality guardrails.
- **Implemented In**: `src/agent/learning/constitution.py:AGENT_CONSTITUTION`, `check_compliance()`; `tests/test_constitution_pin.py`
- **Invariants**: Any edit to AGENT_CONSTITUTION fails CI until a human updates the pin test

#### Evidence-Only Lesson Attribution
- **Rule**: Lessons are attributed only to decisions whose outcomes are measurable. A HOLD or a decision with no subsequent price data produces no lesson.
- **Rationale**: Avoids spurious learning from unmeasurable outcomes.
- **Implemented In**: `src/agent/learning/efficacy.py`, `src/agent/learning/review.py`

### Universe Constraint

#### Tradeable Pool Enforcement
- **Rule**: Agent decisions for symbols outside the current universe are rejected by filter_in_universe() before execution. The executor also checks at execution time.
- **Rationale**: Prevents trading illiquid names, OTC, or symbols for which no data provider is available.
- **Implemented In**: `src/agent/orchestrator.py:filter_in_universe()`, `src/agent/executor.py`
- **Invariants**: Universe is resolved once at startup from config/universe/{market}_base.json; --symbols CLI override replaces it

### Human Steering

#### Human Commands Go Through the Same Gate
- **Rule**: Operator console commands (buy/sell/short/cover/flatten) pass through RiskManager.validate_order() via the executor, never directly to the broker.
- **Rationale**: The human is never locked out but is also never exempt from risk rules.
- **Implemented In**: `src/agent/steering/commands.py:build_human_buy()`, `DecisionExecutor.execute_decision()`

#### HMAC Token Validation (Hard)
- **Rule**: Every command in commands.jsonl must carry a valid HMAC token. Unconfirmed or tampered commands are rejected fail-closed.
- **Rationale**: The daemon runs unattended; its file-drop channel must authenticate the operator.
- **Implemented In**: `src/agent/steering/channel.py:SteeringChannel.read_new_commands()`, `src/agent/steering/security.py`
- **Invariants**: HMAC comparison is constant-time (hmac.compare_digest); token never written to logs or events

### Data Freshness

#### Intraday Feature Auto-Collection (F82)
- **Rule**: On daemon start, gap-backfill per-symbol intraday Parquet features for all universe symbols in a background thread. Append after each session close.
- **Implemented In**: `src/data/intraday/auto.py`, `src/data/intraday/collector.py`
- **Invariants**: Background collector never blocks the agent loop; failures are logged and swallowed

#### Signal Cache TTL
- **Rule**: Price scans cached for cache_ttl_seconds (300s default). Individual price lookups cached for price.cache_seconds (3s). Bounds API rate without staling data excessively.
- **Implemented In**: `src/signals/collector.py`, `src/agent/intraday/bars.py`
