# System Architecture

## System Overview
Autostock has **two distinct orchestration paths** that share the same domain core
(`src/core/`), risk gate (`src/risk/`), and broker abstraction (`src/execution/`):

1. **Strategy path** (original): `TradingEngine` runs pluggable strategies
   (technical / ml / llm / ensemble) per symbol. Used by backtest, paper, and realtime modes.
2. **Agent path** (newer, most actively developed): an agentic LLM portfolio manager reasons
   over the whole book each trading day via the local `claude` CLI, writes machine-readable
   `Decision` lines to a file journal, and a deterministic `DecisionExecutor` places resting
   bracket orders. Used by `--mode agent`.

## Architecture Diagram

```text
                          main.py  (CLI mode dispatch)
                              |
        +---------------------+--------------------------+
        |                     |                          |
        v                     v                          v
   backtest mode        paper / realtime modes       agent mode
        |                     |                          |
        v                     v                          v
  BacktestEngine        TradingEngine             AgentTradingMode
  (SimulatedBroker)     (per-symbol cycle)        +--------------------+
        |                     |                   | AgentTradingLoop   |  brain
        |                     |                   |  -> AgentSession   |  (claude CLI)
        |                     |                   |  -> Journal (files)|
        |                     |                   +---------+----------+
        |                     |                             | decisions.jsonl
        |                     |                             v
        |                     |                   DecisionExecutor       body
        |                     |                             |
        +---------+-----------+--------------+--------------+
                  v                          v
            RiskManager  <----------->  BaseBroker
          (signal -> Order)     (Simulated / Alpaca / KIS)
                  ^
                  |
            src/core/  (models, enums, exceptions — depended on by all)
```

## Component Descriptions

### Strategy path
- **TradingEngine** (`src/trading/engine.py`) — per-symbol cycle: data → strategy → RiskManager →
  broker; also owns polled stop/take-profit exits. Entry points `run_cycle()` (whole universe) and
  `run_cycle_for_symbol()` (realtime).
- **Strategy layer** (`src/strategy/`) — `BaseStrategy` ABC + decorator registry; technical (4),
  ml (4), llm (5), ensemble (2).
- **Trading modes** (`src/trading/modes/`) — `agent.py`, `realtime.py`, `batch.py`.
- **Backtest** (`src/backtest/`) — replays bars through the same RiskManager + strategies against `SimulatedBroker`.

### Agent path
- **AgentTradingMode** (`src/trading/modes/agent.py`) — schedules daily turns (pre-market research /
  intraday / EOD) on `TradingScheduler`; composes orchestrator (brain) with executor (body).
- **AgentTradingLoop** (`src/agent/orchestrator.py`) — sequences turn types, injects context
  (universe, held positions), enforces the universe constraint.
- **AgentSession** (`src/agent/session.py`) — wraps the local `claude -p` CLI with tools enabled;
  one resumable session per US/Eastern trading day.
- **Journal** (`src/agent/journal.py`) — file-based durable memory under `workspace/`: markdown
  theses + append-only `decisions.jsonl`.
- **DecisionExecutor** (`src/agent/executor.py`) — the only thing that places agent orders; reads
  `decisions.jsonl`, applies pool/expiry/circuit-breaker checks, routes through RiskManager (bracket
  mode) → broker, reconciles resting protective legs. Cursor file makes it idempotent.
- **Self-learning / telemetry** (`src/agent/turn_log.py`, `equity_log.py`, `trades_log.py`,
  `review.py`, plus efficacy/lessons modules) — per-turn cost, daily equity vs benchmark, closed
  round-trips, EOD self-review → lessons, lesson attribution, hybrid recall, charter-bounded prompt
  self-rewrite.

### Shared core
- **RiskManager** (`src/risk/manager.py`) — single gate from signal/decision to `Order`. Two behaviors
  selected by `use_bracket_orders`: legacy market-order + polled stop, or resting BRACKET/OCO from supplied levels.
- **BaseBroker** (`src/execution/base.py`) — `SimulatedBroker`, `AlpacaBroker`, `KISBroker`.
- **core** (`src/core/`) — Pydantic models, enums, exceptions; depended on by all, depends on nothing.

## Data Flow (agent turn, simplified)
```text
pre-market research turn  -> AgentSession (claude CLI) -> Journal theses + decisions.jsonl
intraday turn             -> AgentSession -> updated decisions
DecisionExecutor          -> reads decisions.jsonl -> RiskManager (bracket) -> Broker (resting OCO)
EOD turn                  -> review.py -> lessons (self-learning) -> next-day prompt context
```

## Design Patterns
- **Strategy registry** — `BaseStrategy` ABC + decorator registration in `src/strategy/`.
- **Port/adapter (broker)** — `BaseBroker` abstraction; Alpaca/KIS/Simulated adapters.
- **Brain/body split (agent)** — orchestrator reasons (LLM) and journals; deterministic executor places orders.
- **Idempotent journal consumer** — cursor file makes `DecisionExecutor` safe across restarts.

## Layer Dependency Rule (intended)
`trading`/`backtest`/`agent` → `strategy`/`risk`/`execution`/`data`/`signals` → `core`.
`core` depends on nothing.
