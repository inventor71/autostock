# Autostock — Design Document

> Architecture and design rationale for the autostock automated trading system.
> For usage, see [README.md](../README.md); this document covers internal structure,
> design intent, and how to extend the system.
> 한국어 보존본: [DESIGN_KO.md](DESIGN_KO.md) (may lag this canonical English version).

---

## 1. Overview

Autostock is an automated equities trading platform for **US markets** (NYSE/NASDAQ via
Alpaca) and **Korean markets** (KIS — 한국투자증권). It abstracts a single pipeline —
**market data → signal/strategy → risk gate → order execution → telemetry & journaling** —
and exposes **two orchestration paths** over a shared domain core:

- **Strategy path** (original): the same strategy code runs unchanged across **backtest /
  paper / realtime** modes. `TradingEngine` evaluates pluggable strategies per symbol.
- **Agent path** (newer, most actively developed): an agentic LLM **portfolio manager**
  reasons over the whole book each trading day, writes machine-readable `Decision` lines to a
  file journal, and a deterministic `DecisionExecutor` turns them into resting bracket orders
  (`--mode agent`). See §5.8.

The defining stance is **safety-first**: shorting is off by default, position sizing is
risk-budget driven, and a deterministic `RiskManager` gates *every* order — from a strategy,
the LLM, or a human console command — before it reaches a broker.

Core characteristics:

- **Pluggable abstractions** — data providers, brokers, and strategies each implement an
  abstract base (`BaseDataProvider`, `BaseBroker`, `BaseStrategy`), so they swap freely.
- **Strategy variety** — 4 technical, 2 ML, LLM, and ensemble strategies behind one interface.
- **Backtest/live consistency** — backtest and live share the same `RiskManager` and strategy
  logic, minimizing result divergence.
- **LLM prompt self-improvement** — the LLM analyzes backtest results and version-bumps its
  own trading prompt.
- **Agentic PM** — a second path with a **brain/body split**: the LLM advises (journals) and
  deterministic Python (`RiskManager → Broker`) is the sole actuator.

---

## 2. Design Principles

| Principle | How it's applied |
|---|---|
| **Separation of concerns** | Directory split: data / strategy / risk / execution / trading / backtest / agent / signals |
| **Interface-first** | Each layer defines its contract as an ABC; implementations are isolated under `providers/` · `brokers/` |
| **Dependency inversion** | `TradingEngine` depends on base abstractions, not concrete classes (injected via `main.py`) |
| **Type safety** | All domain objects are Pydantic v2 models (`src/core/models.py`); enums in `src/core/types.py` |
| **Externalized config** | Behavior controlled by YAML / env vars with no code changes (`config/`) |
| **Registry pattern** | Strategies self-register via decorator; instantiated by name string |
| **Single risk gate** | One enforcement point — `RiskManager.validate_order()` — that nothing bypasses |

---

## 3. System Architecture

Autostock has **two orchestration paths** sharing the same domain core (`src/core/`), risk
gate (`src/risk/`), and broker abstraction (`src/execution/`):

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
 (SimulatedBroker)     (per-symbol cycle)        +----------------------------+
       |                     |                   | AgentTradingLoop           | brain
       |                     |                   |  -> SignalCollector        |
       |                     |                   |  -> AgentSession           | (claude CLI)
       |                     |                   |  -> Journal (files)        |
       |                     |                   +---------+------------------+
       |                     |                             | decisions.jsonl
       |                     |                             v
       |                     |                   DecisionExecutor              body
       |                     |                   (cursor-idempotent)
       |                     |                             |
       |                     |   [SteeringRuntime + CommandBus — optional]
       |                     |                             |
       +---------+-----------+--------------+--------------+
                 v                          v
           RiskManager  <----------->  BaseBroker
         (signal -> Order)     (Simulated / Alpaca / KIS / Broker API)
                 ^
                 |
           src/core/  (models, enums, exceptions — depended on by all)
```

**Layer dependency rule**: `trading / backtest / agent` → `strategy / risk / execution /
data / signals` → `core`. Only higher layers reference lower ones; `core` depends on nothing.

---

## 4. Core Domain Model

`src/core/` is the single source of truth for types shared across every layer.

### 4.1 Enums (`types.py`)

- `Signal`: `BUY / SELL / HOLD / SELL_SHORT / BUY_TO_COVER` (F54 added short signals)
- `OrderSide`: `buy / sell / sell_short / buy_to_cover` (maps 1:1 to Alpaca's native short sides)
- `OrderType`: `MARKET / LIMIT / STOP / STOP_LIMIT / TRAILING_STOP` (F9 trailing via `trail_price`/`trail_percent`)
- `OrderClass`: `SIMPLE / BRACKET / OCO / OTO`
- `PositionSide`: `LONG / SHORT`
- `TimeFrame`: `1m / 5m / 15m / 30m / 1h / 4h / 1d / 1w / 1mo`
- `TradingMode`: `backtest / paper / live / agent`

### 4.2 Data Models (`models.py`)

```
Bar              Single OHLCV candlestick
TradeSignal      Strategy output (signal, confidence 0-1, sell_pct, metadata)
Order            Broker-bound instruction (side, qty, order_type, bracket/trail legs, ...)
FilledOrder      Confirmed execution (filled_price, filled_at, commission)
OpenOrder        Resting (unexecuted) order at the broker
Position         Open exposure (qty, entry_price, current_price, unrealized_pnl, side)
PortfolioState   Account snapshot (cash, equity, buying_power, positions dict)
                 └ equity is the single source of account value (broker-authoritative)
BacktestResult   Backtest performance (return, Sharpe, MDD, win rate, profit factor, ...)
```

**Design point**: `TradeSignal` carries more than a direction — `confidence` (drives position
sizing) and `sell_pct` (partial liquidation), plus a `metadata` dict for per-strategy context
(e.g. the LLM's rationale).

### 4.3 Agent journal entities (`src/agent/journal.py`)

```
Decision         Machine-readable trade decision; the unit of brain/body hand-off.
                 └ symbol, action, qty, rationale, lessons_cited, prompt_version
                 └ persisted append-only to decisions.jsonl; consumed once (cursor-tracked)
Thesis           LLM conviction for a position — rationale + entry/stop/target levels
LessonRecord     A lesson learned from an outcome; written at EOD, recalled by regime/sector
```

`DecisionAction` literal: `BUY / SELL / HOLD / ADJUST_STOP / SELL_SHORT / BUY_TO_COVER`.

### 4.4 Exceptions (`exceptions.py`)

`AutostockError` (base) → `DataProviderError`, `BrokerError`, `StrategyError`,
`RiskLimitError`, `ConfigurationError`, `InsufficientDataError`.

---

## 5. Layer Detail

### 5.1 Data layer (`src/data/`)

```
BaseDataProvider (ABC)
├─ get_bars(symbol, timeframe, start, end, limit) -> DataFrame   [abstract]
├─ get_latest_price(symbol) -> float                             [abstract]
├─ get_latest_prices(symbols) -> dict   best-effort, partial on failure (NFR-4)
└─ get_multiple_bars(...) -> dict[symbol, DataFrame]             [default]

Implementations:
├─ AlpacaProvider          US realtime/paper data (REST + WebSocket)
├─ YFinanceProvider        free fallback / backtest source
├─ KIS provider            Korean equities market data
└─ YFinanceNewsProvider    news context for LLM strategy
```

All bars follow the `[open, high, low, close, volume]` + `DatetimeIndex` convention, so
strategies are agnostic to the data source. **Best-effort multi-symbol fetch (NFR-4)**:
`get_latest_prices()` returns a partial dict when some symbols fail — one bad symbol must not
block a whole scan; callers tolerate missing keys.

### 5.2 Strategy layer (`src/strategy/`)

Every strategy implements `BaseStrategy`; the core contract is a single method:

```python
generate_signal(symbol, bars, portfolio) -> TradeSignal
```

Two optional hooks support dynamic symbol selection (momentum screening, sector rotation):
`supports_selection() -> bool` and `select_symbols(universe, market_data, portfolio)`.

**Registry** (`registry.py`): `@register_strategy("rsi")` self-registers a class;
`create_strategy("rsi", params)` resolves by name. `main.py` imports strategy modules to
trigger registration, then instantiates the `active_strategies` list from `strategies.yaml`.

| Category | Location | Members |
|---|---|---|
| Technical | `technical/` | MA Crossover, RSI, MACD, Bollinger Bands |
| ML | `ml/` | Random Forest, LSTM (+ `feature_eng.py`) |
| LLM | `llm/` | Claude / OpenAI analysis strategy |
| Ensemble | `ensemble/` | Voting (majority), Weighted |

**ML (`BaseMLStrategy`)** adds `build_features / train / predict / save_model / load_model`;
the base implements the common "load → build features → predict last row" flow. Weights persist
under `models/`.

**Ensemble (`VotingEnsemble`)** collects sub-strategy signals and takes a majority vote, adopting
a signal only above `min_agreement` (default 0.6); confidence = mean confidence × agreement.

**LLM subsystem (`src/strategy/llm/`)** — the most complex module:

```
strategy.py        LLMStrategy — format data → call LLM → parse JSON → TradeSignal
client.py          BaseLLMClient + ClaudeClient / OpenAIClient; factory + exp. backoff retry
data_formatter.py  OHLCV + news → prompt text, token truncation
prompt_manager.py  Prompt versioning (v1, v2, ...), per-version backtest metrics, latest/best
auto_improver.py   Analyze backtest results → ask LLM to improve → new prompt version
```

**Robustness**: LLM output is non-deterministic, so `_parse_llm_response` cascades — ①direct
JSON, ②markdown code-fence extraction, ③regex object extraction, ④keyword fallback (low
confidence). Any failure returns `HOLD` — fail-safe.

### 5.3 Risk layer (`src/risk/`) — the gatekeeper

Converts signals/decisions into actual orders; sits between strategy/agent and broker. **This
is the one enforcement point in the system.**

```
RiskManager
├─ validate_order(...) -> Order | None   single gate from signal/decision to Order
├─ check_stop_loss(portfolio)   -> list[Order]
└─ check_take_profit(portfolio) -> list[Order]

PositionSizer
└─ calculate_shares(...) -> int   min(fixed-pct alloc, risk-based alloc) × confidence, capped by cash
```

Defaults: `max_position_pct=0.1`, `max_portfolio_risk=0.02`, `stop_loss_pct=0.05`,
`take_profit_pct=0.15`, `max_open_positions=10`. **Sizing formula**: take the smaller of
fixed-fraction (`equity × max_position_pct`) and risk-based (`equity × max_portfolio_risk /
stop_loss_pct`), scale by signal confidence, then cap by available cash.

**Dual-mode (structural debt S-2)**: `use_bracket_orders` selects legacy market-order +
polled-exits vs. resting **BRACKET/OCO** orders whose protective legs rest at the exchange.
See §9.

See [§6 Business Rules](#6-key-business-rules) for the shorting switch, circuit breaker, and
bracket-leg validation rules enforced here.

### 5.4 Execution layer (`src/execution/`)

```
BaseBroker (ABC)
├─ submit_order(order) -> FilledOrder
├─ get_position / get_all_positions / get_portfolio_state
├─ get_open_orders / cancel_order / close_position

Implementations:
├─ SimulatedBroker    backtest — immediate fill, cash/position ledger, set_current_price()
├─ AlpacaBroker       US paper/live (Alpaca Trading API)
├─ BrokerApiBroker    Alpaca Broker API sandbox account farm (shares logic via AlpacaShapedBroker)
└─ KisPaperBroker     Korean equities (KIS / pykis)
```

The shared `BaseBroker` contract means callers never know whether they're simulating or
trading live. `BrokerApiBroker` shares request-building / fill-polling / position-mapping with
`AlpacaBroker` via `AlpacaShapedBroker`; **R7** fixed short-cover side mapping
(`sell` → `buy_to_cover`) and made TIF handling fail-closed (unsupported TIF raises rather than
silently downgrading).

**Multi-broker routing**: US → Alpaca, KR → KIS, backtest → Simulated. Broker is selected at
startup via config (`main.py:create_broker()`), not at order time.

### 5.5 Trading orchestration (`src/trading/`)

`TradingEngine.run_cycle()`: fetch portfolio → check risk exits (stop/take first) → load
universe bars → for each strategy, `select_symbols()` then `generate_signal()` per symbol →
risk-evaluate → submit. Each step is try/except-isolated so one symbol/strategy failure
doesn't abort the cycle.

| Mode (`modes/`) | Trigger | Use |
|---|---|---|
| `BatchTradingMode` | APScheduler interval (default 60m) | periodic rebalancing |
| `RealtimeTradingMode` | Alpaca WebSocket bar events | reactive trading (per-symbol `run_cycle_for_symbol`) |
| `AgentTradingMode` | market-time schedule (see §5.8) | agentic LLM PM |

`TradingScheduler` (`scheduler.py`) wraps APScheduler and supports US-market cron jobs
(09:30 ET open, 15:55 ET close) in addition to interval jobs.

### 5.6 Backtest layer (`src/backtest/`)

`BacktestEngine.run(...)` iterates bars after a warmup, updating prices, checking stops/takes,
and passing only `bars.iloc[:i+1]` to the strategy (**look-ahead bias prevention**). It uses the
same `RiskManager` and strategies as live for consistency. `metrics.py` computes
Sharpe/Sortino/Calmar/MDD/win-rate/profit-factor (round-trip based, shared via
`src/core/trades.py::match_round_trips`); `optimizer.py` does grid-search over a param grid.

### 5.7 Monitoring (`src/monitoring/`)

`logger.py` (loguru setup), `alerts.py` (Slack/Telegram, toggled in config), plus health
checkers (account, broker, LLM, process, disk, risk).

### 5.8 Agent path (`src/agent/`) — the LLM portfolio manager

A second orchestration path. Unlike `TradingEngine`'s per-symbol loop, the LLM PM reasons over
**the whole book in one turn**. The **brain/body split** is the central design: the LLM only
advises (journals); only deterministic Python places orders.

```
AgentTradingMode (trading/modes/agent.py)   composes the market-time schedule
├─ AgentTradingLoop (orchestrator.py)   brain: sequences daily turns (research / intraday / EOD)
│   └─ AgentSession (session.py)        wraps local `claude -p` CLI as a per-day session
│        └─ Journal (journal.py)        durable file-based memory
│             ├─ decisions.jsonl        append-only machine-executable Decision lines
│             ├─ positions/<SYM>.md     per-symbol thesis + plan (entry/stop/target)
│             └─ regime / watchlist / lessons
└─ DecisionExecutor (executor.py)       body: reads decisions and executes — the only order path
     ├─ pool / expiry / circuit-breaker checks
     ├─ RiskManager (bracket mode) → Broker
     └─ cursor (.executor_state.json) for idempotent execution
```

**Key design points**:

- **Brain/body split** — the agent only appends proposals to `decisions.jsonl`; the executor is
  the sole actuator and routes every decision through the **same gate** (`RiskManager → Broker`)
  as the other paths.
- **Journal = single source of truth** — the daily CLI session handles intra-day continuity only;
  a new day starts a new session. All durable state lives in `workspace/` files (gitignored).
- **Idempotent execution** — the cursor records how many decision lines were processed, so a
  restart re-submits each bracket exactly once (the exchange then holds the OCO).
- **Advisory/execution time-split** — research can run pre-open (decisions stay pending while
  `is_market_open` is False); execution only happens in regular hours.
- **Telemetry/ledger** — `turn_log` (per-turn cost), `equity_log` (daily equity vs benchmark),
  `trades_log` (closed round-trips), `review.py` (EOD self-review → lessons).

#### 5.8.1 Intraday loop redesign (F3, `src/agent/intraday/`)

Keeps the 15-minute scheduled turn but **(1) injects a structured brief** (eliminating
recompute) and **(2) adds event-driven wake turns** that fire first on market events needing
judgment. Active only with `--steering` (depends on snapshot / RunState / ReconcileWorker);
otherwise falls back to the legacy prompt (behavior-preserving).

- **brief** (`brief.py`): market data from the daemon `BarCache`; account/fills/locks/pending
  approvals from the in-proc `last_snapshot` only (no direct broker calls); human directives
  from SteeringState. Fail-closed: no snapshot → omit the account section.
- **wake detection** (`wake.py`): `new_fill` / `abnormal_move` (ATR×k or volume×m) /
  `watch_trigger` / `protective_reassess`. Reads cache only, non-blocking on the scheduler
  thread. `paused` holds everything; `entries_halted` suppresses only entry-inducing wakes.
- **watch** (`watch_store.py` + agent `watch set/clear/list` tools): append-only `watch.jsonl`;
  fired state tracked separately with an ET-midnight sweep.
- **fill truth** (`get_fills`): Alpaca `/account/activities` (idempotent by activity id) read on
  the bus worker — broker-authoritative, not inferred from prices.
- **concurrency**: one `turn_lock`; per-kind reconcile timers prevent a wake storm from
  starving human reconcile. Tuning under `config/settings.yaml` `intraday:`.

### 5.9 Operator console / steering (`operator-console/`, `src/agent/steering/`)

The layer for a human to **intervene in a running agent in natural language**. The *what/why*
matters most; details live in each component's code.

- **What/why**: the agent (and the console's own LLM) have **no order authority**. When an
  operator gives intent ("trim AAPL by half"), only a **human-confirmed** command travels via
  the repo-root `steering/` file-drop channel (commands/events/snapshot) to the daemon, which
  executes it through the **same `RiskManager → Broker` gate** as every other path. This
  preserves the advisor-only invariant while adding human intervention.
- **Daemon engine** (`src/agent/steering/`, F4): file-drop channel read + snapshot publish +
  single-worker **CommandBus** (broker/cursor serialization, NFR-2) + TurnCoordinator (serializes
  all LLM turns) + RunState (pause/halt). The F3 wake loop (§5.8.1) runs atop this engine.
- **Console** (`operator-console/`, F4): a hard fork of
  [opencode](https://github.com/sst/opencode) rebranded for trading. The LLM only proposes;
  human-confirmed writes are handled by a deterministic layer (structural separation of
  authority). Talks to the daemon only via the file-drop channel.
- **Launcher / daemon management** (F5): the `~/.local/bin/autostock` launcher (install via
  `operator-console/launcher/install.ts`) runs a fail-closed preflight, auto-starts a
  **systemd --user** daemon (or attaches if up), then hands off to the console.
- **Sidebar** (F6): run-state, market, positions, pending approvals, plus account/round-trip
  (win-rate, realized P&L) summary, mouse-drag resizable.

### 5.10 Research signals (`src/signals/`)

`SignalCollector` assembles a pre-research **brief** injected into the agent's research prompt
(TTL-cached so the push path and the agent's pull tools share one fetch). Sources, all
**fail-honest** (a failing source returns an error annotation; the turn proceeds with partial
signals):

- **Movers** — price % / volume-multiple scan.
- **Peer read-through** — propagates a mover to sector peers via a static `PeerMap` (R6/R7).
- **Earnings & IPO calendars** — Finnhub (F61 / F78).
- **Retail sentiment** — StockTwits self-labeled bull/bear, surfaced only as **baseline z-score
  outliers** vs. a symbol's own rolling history (F77; the crowd is ~75% bullish by default, so
  raw ratios carry no signal).

### 5.11 Self-learning (`src/agent/`, charter-bounded)

EOD `review.py` produces `LessonRecord`s; lessons are attributed to decisions via
`lessons_cited` + `prompt_version` on each `Decision`. Guidance prompts may **self-rewrite —
only within an immutable `CONSTITUTION`** (`constitution.py`), with a compliance check and
automatic rollback. Constitution changes require user approval; prompt swaps stay automatic.
The machinery ships **inert** by default (`AgentTradingLoop._rewrite_fn` is `None`).

---

## 6. Key Business Rules

These invariants are enforced in code, not prompts (full catalog:
`aidlc-docs/codekb/business-rules.md`):

- **Single risk gate** — no `BaseBroker.submit_order()` without a `RiskManager`-produced
  `Order`. LLM, strategy, and human commands all pass through it.
- **Position size limit** — no position exceeds `max_position_pct` of equity.
- **Portfolio circuit breaker** — drawdown past `circuit_breaker_pct` blocks *new* entries
  (closing/reducing is never blocked).
- **Agent order authority** — only `DecisionExecutor` places orders in agent mode; decisions are
  consumed exactly once (cursor + atomic `os.replace()`).
- **Shorting off by default** — `shorting_enabled=false`; new shorts rejected when off, but
  covering an existing short is always allowed. Short market halt (SPY up ≥3%) and individual
  stock halt (symbol up ≥10%) further gate new shorts.
- **Bracket-leg validation** — long: stop below / take above entry; short: inverse.
- **Fail-closed TIF (R7)** — unsupported `time_in_force` raises rather than silently
  downgrading (supported: `day`, `gtc`, `ioc`, `fok`).
- **Advisor-only console** — every human command goes through the same risk gate; the console
  LLM is advisory.
- **Single writer for broker ops (NFR-2)** — all broker mutations on one CommandBus worker
  thread.

---

## 7. Extension Guides

### Add a strategy
1. Create `src/strategy/<category>/my_strategy.py`.
2. Subclass `BaseStrategy` + `@register_strategy("my_strategy")`.
3. Implement `generate_signal()` (override `select_symbols()` if needed).
4. Add the import to `main.py` (triggers registration).
5. Define it in `config/strategies.yaml` and add to `active_strategies`.

### Add a data provider
1. Implement `BaseDataProvider` in `src/data/providers/my_provider.py`.
2. Implement `get_bars` / `get_latest_price` (honor the OHLCV + DatetimeIndex convention).
3. Add a branch in `main.py:create_data_provider()`.

### Add a broker
1. Implement `BaseBroker` in `src/execution/brokers/my_broker.py`.
2. Implement all abstract methods.
3. Add a branch in `main.py:create_broker()`.

---

## 8. Configuration (`config/`)

```
config.py        Pydantic Settings — merges YAML + .env + env vars; get_settings() (lru_cache singleton)
settings.yaml    app / broker / data / trading / risk / backtest / LLM / signals / intraday
strategies.yaml  strategy definitions, params, active list, ensemble composition
.env             API keys (Alpaca / Anthropic / OpenAI / Finnhub / KIS) — never committed
```

**Precedence**: CLI args > env vars > `.env` > YAML > code defaults. Nested keys via
`env_nested_delimiter="__"` (e.g. `RISK__STOP_LOSS_PCT`). `AUTOSTOCK_ENV_FILE` lets the test
harness load a separate `.env.test`.

### External integrations

| Integration | Purpose | Auth |
|---|---|---|
| Alpaca Trading API | US order execution, portfolio (paper + live) | `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` |
| Alpaca Broker API | Sandbox account-farm creation/funding | `BROKER_API_KEY` / `BROKER_SECRET_KEY` |
| Alpaca Data API | US bars, quotes, news (REST + WebSocket) | same as Trading |
| KIS OpenAPI (`pykis` 2.1.6) | Korean equities paper broker + data | `KIS_APP_KEY` / `KIS_APP_SECRET` / `KIS_ACCOUNT_NO` |
| local `claude` CLI | Agent brain (AgentSession) | OAuth subscription (`~/.claude/`) |
| Anthropic / OpenAI SDK | LLM strategy signals | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` |
| Finnhub | Earnings + IPO calendars (signals) | `FINNHUB_API_KEY` |
| StockTwits | Retail sentiment (unauthenticated, ~200 req/hr) | none |
| Yahoo Finance | Fallback data + news | none |

All persistence is **file-based** (JSONL logs, journal files, file-drop IPC) — no relational
or NoSQL database. KIS specifics: 모의투자 (paper) has no stop-limit (`ORD_DVSN=22`, live-only);
KIS live trading is pending.

---

## 9. Known Structural Debt

> Found during design review. See `aidlc-docs/codekb/` for current detail.

- **S-2** — `RiskManager` is dual-mode (`use_bracket_orders`): legacy market-order + polled exits
  vs. resting BRACKET/OCO; the two modes diverge in behavior.
- **S-3** — some `src/` modules reach into the config singleton directly (layer violation vs.
  injection through `main.py`).
- **Short logic** — `PositionSide.SHORT` and short signals exist (F54/F60), but some risk/execution
  paths still assume long-only in places.

> **Resolved** (historical): realtime `engine.symbols`→`universe` mismatch and per-bar universe
> reload (now `run_cycle_for_symbol`); backtest fidelity (round-trip metrics + intraday OCO
> triggers via bar high/low); fractional-position sell truncation; single account-value source
> (`PortfolioState.equity`).

---

*This document is derived from the codebase knowledge base (`aidlc-docs/codekb/`) and source
(`src/`, `config/`, `main.py`). Update it alongside structural changes.*
