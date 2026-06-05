# Business Rules

## Rules by Domain

### Risk & Execution
#### Single risk gate
- **Rule**: Every signal/decision must pass through `RiskManager` before becoming an `Order`.
- **Rationale**: One enforcement point for sizing and risk limits; nothing bypasses it.
- **Implemented In**: `src/risk/manager.py`
- **Invariants**: No broker order is placed without a RiskManager-produced `Order`.

#### Bracket / OCO protective legs
- **Rule**: In bracket mode (`use_bracket_orders`), entries place resting BRACKET/OCO orders with
  stop + take-profit legs derived from supplied (often LLM-suggested) levels; protective legs are
  reconciled after fills.
- **Rationale**: Defense-in-depth — protection rests at the exchange, not only in a polling loop.
- **Implemented In**: `src/risk/manager.py`, `src/agent/executor.py`

#### Agent order authority
- **Rule**: In agent mode, only `DecisionExecutor` places orders — by reading `decisions.jsonl`.
- **Rationale**: Brain (LLM) reasons and journals; body (deterministic executor) is the sole actuator.
- **Implemented In**: `src/agent/executor.py`
- **Invariants**: Decisions are consumed once (cursor file makes execution idempotent across restarts).

#### Execution guards
- **Rule**: Executor applies pool/expiry/circuit-breaker checks before routing a decision to risk/broker.
- **Implemented In**: `src/agent/executor.py`

### Universe & Scheduling
#### Universe constraint
- **Rule**: The agent may only act on symbols in the injected universe; the orchestrator enforces this.
- **Implemented In**: `src/agent/orchestrator.py`, `src/universe/`

#### Trading-day turns
- **Rule**: One resumable agent session per US/Eastern trading day; turns scheduled at pre-market
  (research), intraday, and EOD via market-cron.
- **Implemented In**: `src/trading/modes/agent.py`, `TradingScheduler`

### Self-learning (charter-bounded)
- **Rule**: EOD self-review produces lessons; lessons are attributed to decisions (`lessons_cited` +
  `prompt_version`); guidance prompts may self-rewrite **only within an immutable CONSTITUTION**, with a
  compliance check and rollback. Constitution changes require user approval; prompt swaps stay automatic.
- **Rationale**: Bounded autonomy — the agent improves its own prompts without escaping fixed guardrails.
- **Implemented In**: `src/agent/review.py` + efficacy/lessons/rewrite modules (tracks F64/F65/F66/F67/F68).

### Markets
#### Multi-broker market routing
- **Rule**: US equities route through Alpaca; Korean equities through KIS; backtests through Simulated.
- **Implemented In**: `src/execution/brokers/`
- **Note**: KIS paper (모의투자) does not support stop-limit; stop orders are live-only.
