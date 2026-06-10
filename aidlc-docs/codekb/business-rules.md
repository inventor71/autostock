# Business Rules

## Rules by Domain

### Risk & Execution

#### Single Risk Gate
- **Rule**: Every signal or decision — whether from an LLM, a strategy, or a human console command — must pass through `RiskManager.validate_order()` before any order reaches the broker.
- **Rationale**: One enforcement point for sizing and risk limits; nothing bypasses it, not even human steering.
- **Implemented In**: `src/risk/manager.py`, `src/agent/executor.py`, `src/agent/steering/bus.py`
- **Invariants**: No `BaseBroker.submit_order()` call is made without a RiskManager-produced `Order`.

#### Position Size Limit
- **Rule**: No single position may exceed `RiskConfig.max_position_pct` (default 5%) of total portfolio equity.
- **Rationale**: Concentration risk — a single bad trade cannot destroy the account.
- **Implemented In**: `src/risk/manager.py`, `src/risk/position_sizer.py`
- **Invariants**: PositionSizer derives quantity from available capital × max_position_pct; oversized orders are rejected.

#### Portfolio Circuit Breaker
- **Rule**: If total portfolio drawdown exceeds `RiskConfig.circuit_breaker_pct` (default 2%), no new long entries are accepted until the session resets.
- **Rationale**: Stops runaway losses from compounding during a bad market day.
- **Implemented In**: `src/risk/manager.py`, `src/agent/executor.py`
- **Invariants**: Closing or reducing existing positions is never blocked by the circuit breaker.

#### Bracket / OCO Protective Legs
- **Rule**: In bracket mode (`use_bracket_orders=True`), entries place resting BRACKET/OCO orders with stop + take-profit legs derived from supplied levels (often LLM-suggested); protective legs are reconciled after fills.
- **Rationale**: Defense-in-depth — protection rests at the exchange, not only in a polling loop.
- **Implemented In**: `src/risk/manager.py`, `src/agent/executor.py`

#### Agent Order Authority
- **Rule**: In agent mode, only `DecisionExecutor` places orders — by reading `decisions.jsonl`. The LLM orchestrator never calls the broker directly.
- **Rationale**: Brain (LLM) reasons and journals; body (deterministic executor) is the sole actuator.
- **Implemented In**: `src/agent/executor.py`
- **Invariants**: Decisions are consumed exactly once (cursor file + atomic `os.replace()` makes execution idempotent across restarts).

#### Execution Guards
- **Rule**: Before routing a decision to risk/broker, the executor applies pool-capacity, expiry, and circuit-breaker checks.
- **Implemented In**: `src/agent/executor.py`

### Shorting Rules (F60 + F54)

#### Shorting is OFF by Default
- **Rule**: `RiskConfig.shorting_enabled` ships as `false`. Every new short entry (from agent, `/short` console command, or auto-flip) is rejected when disabled.
- **Rationale**: Unlimited theoretical loss; must be an explicit opt-in per deployment.
- **Implemented In**: `src/risk/manager.py`
- **Invariants**: Covering an existing short (BUY to close) is always allowed — the rule never traps an existing position.

#### Short Market Halt
- **Rule**: If SPY is up ≥ `short_market_halt_threshold_pct` (default 3%), reject all new short entries.
- **Rationale**: Avoid shorting into a broad market rally (short squeeze risk).
- **Implemented In**: `src/risk/manager.py`

#### Individual Stock Short Halt
- **Rule**: If a symbol is already up ≥ `individual_stock_halt_pct` (default 10%) today, reject new short entries for that symbol.
- **Rationale**: High short-squeeze risk on already-elevated stocks.
- **Implemented In**: `src/risk/manager.py`

#### Short Bracket Leg Validation
- **Rule**: For SHORT bracket orders — stop loss must be ABOVE entry, take profit must be BELOW entry (inverse of long brackets).
- **Rationale**: Directionally opposite legs for shorts vs. longs.
- **Implemented In**: `src/risk/manager.py`, `src/agent/steering/gate.py`

### Bracket / OCO Structural Rules (F9)

#### Trail Order Exclusivity
- **Rule**: Trailing stop orders must specify exactly one of `trail_price` or `trail_percent` — not both, not neither.
- **Rationale**: Broker APIs reject ambiguous trail parameters.
- **Implemented In**: `src/agent/steering/gate.py`

#### Supported Order Classes (v1)
- **Rule**: Agent mode supports SIMPLE, BRACKET, OCO order classes. OTO (one-triggers-other) is not supported in v1.
- **Implemented In**: `src/agent/steering/gate.py`

#### Extended Hours Exclusion for OCO
- **Rule**: OCO orders do not set `extended_hours=True`.
- **Rationale**: Alpaca's DAY+LIMIT restriction makes extended-hours OCO legs unreliable.
- **Implemented In**: `src/execution/brokers/alpaca_broker.py`

#### Fail-Closed TIF Enforcement (R7)
- **Rule**: Brokers reject orders with unsupported `time_in_force` values rather than silently downgrading them. Supported TIF values are `day`, `gtc`, `ioc`, `fok`.
- **Rationale**: Silent TIF downgrades caused short-cover orders to be submitted with incorrect semantics. Fail-closed forces the error to the surface.
- **Implemented In**: `src/execution/brokers/broker_api_broker.py`, `src/risk/manager.py` (`_SUPPORTED_TIF`)

### Universe & Scheduling

#### Universe Constraint
- **Rule**: The agent may only act on symbols in the injected trading universe; the orchestrator enforces this at turn assembly.
- **Implemented In**: `src/agent/orchestrator.py`, `src/universe/`

#### Trading-Day Turn Sequence
- **Rule**: One resumable agent session per US/Eastern trading day; turns scheduled at pre-market (research), intraday (event-driven), and post-close (EOD review).
- **Implemented In**: `src/trading/modes/agent.py`, `TradingScheduler`

#### Intraday Wake Conditions (F3)
- **Rule**: Intraday turns trigger only on: (a) abnormal price move ≥ ATR × 1.5, (b) volume spike, (c) news diff detected (15-min poll), or (d) human console command.
- **Rationale**: Prevents costly LLM calls on every tick; only meaningful events warrant re-analysis.
- **Implemented In**: `src/agent/intraday/wake.py`, `src/agent/intraday/abnormal.py`

### Self-Learning (Charter-Bounded)

#### Constitution-Bounded Self-Rewrite
- **Rule**: EOD self-review produces lessons; lessons are attributed to decisions (`lessons_cited` + `prompt_version`); guidance prompts may self-rewrite **only within an immutable CONSTITUTION**, with a compliance check and rollback. Constitution changes require user approval; prompt swaps stay automatic.
- **Rationale**: Bounded autonomy — the agent improves its own prompts without escaping fixed guardrails.
- **Implemented In**: `src/agent/review.py`, `src/agent/constitution.py`, efficacy/lessons/rewrite modules (F64/F65/F66/F67/F68)
- **Invariants**: `AgentTradingLoop._rewrite_fn` is `None` by default; self-rewrite machinery shipped inert (F64).

### Steering / Human Intervention

#### Advisor-Only Console Invariant
- **Rule**: The operator-console LLM is advisory only; the human operator must confirm commands. All confirmed commands travel via the `steering/` file-drop channel and the daemon routes them through the same `RiskManager → Broker` gate.
- **Rationale**: No shortcut around the risk gate, even for human-initiated orders.
- **Implemented In**: `src/agent/steering/runtime.py`, `operator-console/`

#### Single Writer for Broker Operations (NFR-2)
- **Rule**: All broker mutations run on exactly one CommandBus worker thread. No concurrent broker access from different command sources.
- **Rationale**: Prevents race conditions between LLM executor and human steering commands.
- **Implemented In**: `src/agent/steering/bus.py`

#### Steering is Optional (NFR-8)
- **Rule**: When `--steering` flag is absent, the daemon runs identically to pre-steering. No SteeringRuntime is constructed.
- **Rationale**: Backward compatibility — existing deployments without console are unaffected.
- **Implemented In**: `main.py`

### Market Data

#### Best-Effort Multi-Symbol Fetch (NFR-4)
- **Rule**: `get_latest_prices()` returns a partial dict when some symbols fail; callers must tolerate missing keys. One bad symbol must not block the entire scan.
- **Implemented In**: `src/data/base.py`, all provider implementations

#### Fail-Honest Signal Collection
- **Rule**: SignalCollector and agent tool functions return per-source error annotations rather than propagating exceptions. The research turn proceeds with partial signals if any source fails.
- **Implemented In**: `src/signals/collector.py`, `src/agent/tools/market.py`

### Multi-Broker Routing

#### Market-Specific Broker Routing
- **Rule**: US equities → Alpaca; Korean equities → KIS; backtests → SimulatedBroker. Broker selection is set at startup via config, not at order time.
- **Implemented In**: `main.py` (`create_broker()`), `src/execution/brokers/`
- **Note**: KIS paper (모의투자) does not support stop-limit (`ORD_DVSN=22`) — stop orders are live-only.
