# System Architecture (Reverse-Engineered)

> This complements `docs/DESIGN.md`. DESIGN.md documents the data → strategy →
> risk → execution pipeline well, but it predates and **does not describe the
> `src/agent/` subsystem** — which is now the most actively developed path
> (`--mode agent`, ~20 of the last 25 commits). This file fills that gap and
> gives the true top-level picture.

## System Overview

Autostock is a US-equities automated trading framework with **two distinct
orchestration paths** that share the same domain core (`src/core/`), risk gate
(`src/risk/`), and broker abstraction (`src/execution/`):

1. **Strategy path** (the original): `TradingEngine` runs pluggable strategies
   (technical / ML / LLM / ensemble) per symbol. Used by backtest, paper, and
   realtime modes.
2. **Agent path** (the new): an agentic LLM "portfolio manager" reasons over the
   whole book each day via the `claude` CLI, writes machine-readable `Decision`
   lines to a file journal, and a deterministic `DecisionExecutor` places resting
   bracket orders. Used by `--mode agent`.

## Top-Level Component Map (text)

```
                          main.py  (CLI mode dispatch)
                              |
        +---------------------+--------------------------+
        |                     |                          |
        v                     v                          v
   backtest mode        paper / live modes           agent mode
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
          (signal -> Order)         (Simulated / Alpaca)
                  ^
                  |
            src/core/  (models, types, exceptions — depended on by all)
```

## Component Descriptions

### Strategy path
- **TradingEngine** (`src/trading/engine.py`) — per-symbol cycle: data → strategy
  → RiskManager → broker; also owns polled stop/take-profit exits. Two entry
  points: `run_cycle()` (whole universe) and `run_cycle_for_symbol()` (realtime).
- **Strategy layer** (`src/strategy/`) — `BaseStrategy` ABC + decorator registry;
  technical (4), ml (2), llm (6-module subsystem), ensemble (2).
- **Backtest** (`src/backtest/`) — replays bars through the same RiskManager +
  strategies against `SimulatedBroker`.

### Agent path (new — not in DESIGN.md)
- **AgentTradingMode** (`src/trading/modes/agent.py`) — schedules the daily turns
  (pre-market research / intraday / EOD) on `TradingScheduler`; composes the
  orchestrator (brain) with the executor (body).
- **AgentTradingLoop** (`src/agent/orchestrator.py`) — sequences turn types,
  injects context (universe, held positions), enforces the universe constraint.
- **AgentSession** (`src/agent/session.py`) — wraps the local `claude -p` CLI with
  tools enabled; one resumable session per US/Eastern trading day.
- **Journal** (`src/agent/journal.py`) — file-based durable memory under
  `workspace/`: markdown theses + append-only `decisions.jsonl`.
- **DecisionExecutor** (`src/agent/executor.py`) — the only thing that places
  agent orders; reads `decisions.jsonl`, applies pool/expiry/circuit-breaker
  checks, routes through RiskManager (bracket mode) → broker, reconciles resting
  protective legs. Cursor file makes it idempotent.
- **Telemetry/ledger** (`src/agent/turn_log.py`, `equity_log.py`, `trades_log.py`,
  `review.py`) — per-turn cost, daily equity vs benchmark, closed round-trips,
  EOD self-review → lessons.

### Shared core
- **RiskManager** (`src/risk/manager.py`) — the single gate from signal/decision
  to `Order`. Two behaviors selected by `use_bracket_orders`: legacy market-order
  + polled stop, or resting BRACKET/OCO from supplied levels.
- **BaseBroker** (`src/execution/base.py`) — `SimulatedBroker`, `AlpacaBroker`.
- **core** (`src/core/`) — Pydantic models, enums, exceptions; depended on by all,
  depends on nothing.

## Integration Points
- **External APIs**: Alpaca (data + trading), yfinance (data + news), Anthropic /
  OpenAI (LLM strategy), local `claude` CLI subprocess (agent brain).
- **Data stores**: none (file-based `workspace/` journal + JSONL logs; no DB).
- **Scheduler**: APScheduler via `TradingScheduler` (interval + US-market cron).

## Layer Dependency Rule (intended)
`trading`/`backtest`/`agent` → `strategy`/`risk`/`execution`/`data` → `core`.
`core` depends on nothing. **Deviation observed**: several `src/` modules reach
back into `config.config.get_settings()` directly — see code-quality-assessment.md
finding S-3.
