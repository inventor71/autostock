# Domain Entities

## Entity Catalog

### Bar
- **Purpose**: A single OHLCV candle — the basic market-data unit consumed by strategies,
  the backtester, and signal detectors.
- **Key Fields**: `timestamp: datetime`, `open/high/low/close: float`, `volume: float`
- **Relationships**: Aggregated into DataFrames by `BaseDataProvider`; consumed by
  `BaseStrategy`, `BacktestEngine`, `SignalDetector` (early session), `SurgeDetector`.
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Fetched fresh per cycle/turn from a data provider; never persisted long-term
  except in the early-session buffer and the intraday Parquet feature store.

### TradeSignal
- **Purpose**: The output of a strategy — a proposed action with confidence, consumed by
  `RiskManager`.
- **Key Fields**: `symbol`, `signal: Signal` (BUY/SELL/HOLD/SELL_SHORT/BUY_TO_COVER),
  `confidence: [0,1]`, `sell_pct: [0,1]`, `strategy_name`, `timestamp`, `metadata: dict`
  (carries `key_levels`/`atr` for bracket construction)
- **Relationships**: Produced by `BaseStrategy` implementations; consumed by
  `RiskManager.evaluate_signal()`.
- **Defined In**: `src/core/models.py`
- **Lifecycle**: Ephemeral, generated per cycle, immediately converted to an `Order` or
  discarded (HOLD).

### Order
- **Purpose**: A directive to a broker — the sole output of the risk gate before execution.
- **Key Fields**: `symbol`, `side: OrderSide`, `qty`, `order_type` (market/limit/stop/
  stop_limit/trailing_stop), `limit_price?`, `stop_price?`, `order_class` (simple/bracket/
  oco/oto), `take_profit_price?`, `stop_loss_price?`, `trail_price?`/`trail_percent?`,
  `extended_hours`, `client_order_id`, `time_in_force`
- **Relationships**: Produced by `RiskManager`; consumed by `BaseBroker.submit_order()`.
- **Defined In**: `src/core/models.py:32-127`
- **Lifecycle**: Validated at construction (`@model_validator` enforces bracket/OCO leg
  geometry — short positions have inverted stop/target ordering vs. long); submitted once,
  never mutated in place.

### FilledOrder
- **Purpose**: A broker's confirmation that an order executed.
- **Key Fields**: `order_id`, `symbol`, `side`, `qty`, `filled_price`, `filled_at: datetime`,
  `commission`
- **Relationships**: Returned by `BaseBroker.submit_order()`/`close_position()`; feeds
  `match_round_trips()` for P&L attribution.
- **Defined In**: `src/core/models.py:130-137`
- **Lifecycle**: Immutable execution record; appended to trade ledgers.

### OpenOrder
- **Purpose**: A resting order reconciliation record (bracket legs still live at the
  exchange).
- **Key Fields**: `order_id`, `symbol`, `side`, `order_type`, `qty`, `limit_price?`,
  `stop_price?`
- **Relationships**: Returned by `BaseBroker.get_open_orders()`; used by polled stop/
  take-profit backups to avoid double-protecting a symbol.
- **Defined In**: `src/core/models.py:140-149`
- **Lifecycle**: Polled per cycle; not persisted independently.

### Position
- **Purpose**: A current holding (direction-aware, F54).
- **Key Fields**: `symbol`, `qty` (always positive — direction lives in `side`),
  `side: PositionSide` (LONG/SHORT), `avg_entry_price`, `current_price`, `unrealized_pnl`
  (sign convention: short P&L = cost − market_value), `cost_basis` (= qty × avg_entry_price)
- **Relationships**: Held in `PortfolioState.positions`; read/written by `RiskManager`,
  `DecisionExecutor`, console account-truth readers.
- **Defined In**: `src/core/models.py:152-178`
- **Lifecycle**: Refreshed via `update_price()` each cycle from the broker's latest price;
  authoritative copy always lives at the broker, never independently persisted as truth.

### PortfolioState
- **Purpose**: A full account snapshot.
- **Key Fields**: `cash`, `equity` (source of truth — never recomputed from positions to
  avoid silent divergence from stale prices), `positions: dict[symbol → Position]`,
  `timestamp`, `.position_count` (property)
- **Relationships**: Returned by `BaseBroker.get_portfolio_state()`; feeds `RiskManager`
  sizing/limits and the published `snapshot.json`.
- **Defined In**: `src/core/models.py:181-194`
- **Lifecycle**: Fetched fresh per cycle/turn; not stored beyond the current snapshot except
  in `equity.jsonl` (EOD append) and benchmark `EquitySnapshot` series.

### Decision
- **Purpose**: The agent's (or human's) machine-readable trading action — the append-only
  unit of the LLM PM's journal.
- **Key Fields**: `ts`, `symbol`, `action: DecisionAction` (BUY/SELL/HOLD/ADJUST_STOP/
  SELL_SHORT/BUY_TO_COVER), `source` ("agent"|"human"), `confidence`, `sell_pct`, `limit`/
  `stop`/`target` (LLM-suggested levels → RiskManager bracket), `turn_id`, `thesis_ref`,
  `valid_until`, `reason`, `lessons_cited` (F62 attribution), `prompt_version` (default
  "seed"), `aggressiveness` + `grading_horizon_days` (F85)
- **Relationships**: Written to `decisions.jsonl` by the agent's Claude CLI session (async
  append), then post-hoc stamped (prompt_version/lessons_cited) by Python via an atomic
  full-file rewrite (`restamp_decisions`); consumed one-at-a-time by `DecisionExecutor`.
- **Defined In**: `src/agent/journal.py:55+`
- **Lifecycle**: Immutable once written except for the one-time restamp; each line is
  eventually marked terminal (executed or legitimately skipped) in `.executor_state.json`
  and never reprocessed.

### DecisionOutcome
- **Purpose**: The realized result of a Decision — links execution, round-trip P&L, and
  price path for self-learning grading.
- **Key Fields**: `decision`, `execution: ExecutionRecord?`, `round_trip: RoundTrip?`
  (entry_price, exit_price, return_pct, realized_pnl), `price_path: list[OHLC]`,
  `excess: float?` (benchmark-relative return, direction-aware), `mature` (F85 grading
  horizon elapsed), `holding_days`, `decision_index`
- **Relationships**: Assembled by `src/agent/quality/collector.py`; consumed by
  `LessonEfficacy` aggregation and the EOD quality snapshot.
- **Defined In**: `src/agent/quality/models.py:40+`
- **Lifecycle**: Recomputed each EOD review turn from the journal + broker fills; not an
  independently persisted append-only record (derived).

### LessonRecord
- **Purpose**: A structured trading lesson written during EOD self-review.
- **Key Fields**: `lesson_id`, `date`, `category`, `signal_used`, `outcome`, `takeaway`,
  `regime` (F62 tag), `sector` (F62 tag); `times_applied` is deprecated in favor of the pure
  `applied_counts()` function (never an in-place increment on an append-only file).
- **Relationships**: Written to `lessons.jsonl`; ranked/filtered by
  `src/agent/learning/recall.py` (F65) for injection into future prompts; aggregated into
  `LessonEfficacy` by `src/agent/learning/efficacy.py` (F62).
- **Defined In**: `src/agent/journal.py:36+`
- **Lifecycle**: Append-only; efficacy trusted only once `applied_n ≥ MIN_EFFICACY_SAMPLE`
  (20).

### LessonEfficacy
- **Purpose**: Pure aggregation of how well a lesson (or prompt version) has performed.
- **Key Fields**: `lesson_id`, `applied_n` (sample size with measurable excess), `win_rate`,
  `avg_excess` (F85: normalized by holding_days so 2-day and 45-day holds are comparable)
- **Relationships**: Computed from `DecisionOutcome` history; consumed by `recall.py` ranking
  and the EOD prompt.
- **Defined In**: `src/agent/learning/efficacy.py:29`
- **Lifecycle**: Recomputed on demand (pure function over the outcome history), never
  independently persisted.

### WatchTrigger
- **Purpose**: An agent-registered intraday price condition ("E1") that fires a targeted
  reactive turn.
- **Key Fields**: `id`, `symbol`, `condition` (price_above/price_below/close_above/
  close_below), `level`, `intent` (free text, e.g. "ADJUST_STOP→tighten to 180"),
  `thesis_ref`, `valid_until` (ET date, swept at ET-midnight daily)
- **Relationships**: Persisted via `watch_store.py`; evaluated by `WakeDetector` each 5s tick
  against cached prices/bars only (never a synchronous broker fetch).
- **Defined In**: `src/agent/intraday/records.py:38+`
- **Lifecycle**: Marked fired only at actual fire time (not detect time), so a timed-out or
  never-run wake never silently consumes a watch.

### WakeEvent
- **Purpose**: A typed, symbol-scoped intraday event that triggers (or joins a coalesced)
  agent wake turn.
- **Key Fields**: `kind: WakeKind` (new_fill / abnormal_move / watch_trigger /
  protective_reassess / agent_trigger), `symbol`, `reason`, `payload`, `detected_ts`,
  `entry_inducing` (suppressed under `entries_halted`)
- **Relationships**: Emitted by `WakeDetector`, `TriggerEvaluator` (agent_trigger kind);
  consumed by `orchestrator.run_wake()`.
- **Defined In**: `src/agent/intraday/records.py:116+`
- **Lifecycle**: Buffered/coalesced into one turn; lost (by design, safety over data loss) if
  the wake turn times out.

### FillEvent
- **Purpose**: One broker fill, keyed by its broker activity id for idempotent wake
  detection.
- **Key Fields**: `fill_id` (idempotency key), `symbol`, `qty`, `price`, `side` ("buy"|
  "sell"), `kind` ("entry"|"protective"|"unknown"), `ts` (tz-aware UTC)
- **Relationships**: Sourced from `BaseBroker.get_fills(since)`; drives `new_fill` WakeEvents.
- **Defined In**: `src/agent/intraday/records.py:86+`
- **Lifecycle**: One wake per `fill_id` — never re-fires for the same activity.

### TriggerSpec (F88)
- **Purpose**: A self-authored, long-horizon macro/news predicate the agent registers to
  wake itself later.
- **Key Fields**: `id` (kebab-case slug, ≤64 chars), `thesis` (≤2000 chars), `cadence`
  ("hourly"|"daily"), `expires: datetime` (required), `sources: list[SourceRef]`,
  `primary_symbol` (else "MACRO"), `entry_inducing` (default True), `created`
- **Relationships**: Stored/CRUD'd by `TriggerStore`; evaluated by `TriggerEvaluator` in a
  sandbox (no imports/network/file ops in the predicate source, static-screened, ≤16KB); a
  fired trigger produces an `agent_trigger` WakeEvent.
- **Defined In**: `src/agent/triggers/models.py:117+`
- **Lifecycle**: Create-only registration (re-registering an id errors); capped at 64 active
  triggers; disabled automatically after 3 consecutive evaluation errors.

### SourceRef / Verdict (F88)
- **Purpose**: `SourceRef` declares what data a trigger predicate needs (a named internal
  signal or an allow-listed webfetch URL); `Verdict` is the predicate's strictly-typed
  return value.
- **Key Fields**: `SourceRef`: `kind`, `name`|`url`, `params`, `key`. `Verdict`: `fire`
  (strict bool coercion, not truthy), `why` (≤500 chars, truncated).
- **Relationships**: `SourceRef` resolved by `src/agent/triggers/fetch.py` (brokered ctx
  injection); `Verdict` returned from sandboxed predicate execution.
- **Defined In**: `src/agent/triggers/models.py:93+`
- **Lifecycle**: Ephemeral per evaluation tick.

### SteeringCommand
- **Purpose**: A human operator's instruction to the running daemon.
- **Key Fields**: `id` (idempotency/correlation key), `ts`, `verb: SteeringVerb`, `args`,
  `confirmed` (must be True), `token` (HMAC, validated then dropped before any log/event),
  `source` ("human")
- **Relationships**: Written by `operator-console/src/filedrop.ts` to `commands.jsonl`; read
  by `src/agent/steering/channel.py`; gated by `src/agent/steering/gate.py` before reaching
  `DecisionExecutor`.
- **Defined In**: `src/agent/steering/records.py:94+`
- **Lifecycle**: Dedup'd by id via a day-scoped persisted processed-id set; unconfirmed,
  bad-token, or malformed commands are rejected (never silently dropped — a rejection
  outcome is always recorded).

### SteeringEvent
- **Purpose**: The daemon's outcome/notification stream back to the operator console.
- **Key Fields**: `id`, `corr_id` (the originating command's id), `kind`, `payload` (never
  contains secrets/tokens)
- **Relationships**: Written by the daemon (single writer) to `events.jsonl`; tailed by the
  console for the sidebar/UI.
- **Defined In**: `src/agent/steering/records.py:116+`
- **Lifecycle**: Append-only, never rewritten.

### PlaceOrderArgs (F9)
- **Purpose**: The structured, Alpaca-shaped order input accepted from human steering
  commands and the console's MCP order tools.
- **Key Fields**: `symbol`, `side` (buy/sell/sell_short/buy_to_cover), `qty`|`notional`
  (mutually exclusive), `order_type`, `time_in_force`, `limit_price`/`stop_price`/
  `trail_price`/`trail_percent`, `order_class` (simple/bracket/oco), `take_profit`,
  `stop_loss`, `force` (overrides budget/pool/breaker limits but never price-sanity or the
  shorting master switch)
- **Relationships**: Validated at three layers — zod (console, cross-field), a
  degenerate-value check (console, catches 0.01 placeholders), and Pydantic `extra="forbid"`
  + `RiskManager` sizing/price-sanity (daemon, final authority).
- **Defined In**: `src/agent/steering/records.py`
- **Lifecycle**: Ephemeral per command; converted to an `Order` by `RiskManager`'s
  human-order gate.

### RiskManager Configuration Entities
- **Purpose**: The parameters governing the single order gate.
- **Key Fields**: `max_position_pct` (0.1), `max_portfolio_risk` (0.02), `stop_loss_pct`
  (0.05), `take_profit_pct` (0.15), `max_open_positions` (10), `max_stop_distance_pct`
  (0.12), `atr_stop_multiple` (3.0), `market_halt_threshold_pct` (-0.03), `shorting_enabled`
  (F60, default False), short-specific overrides (`short_stop_loss_pct`,
  `short_take_profit_pct`, `short_max_stop_distance_pct`,
  `short_market_halt_threshold_pct`), `individual_stock_halt_pct` (0.10, squeeze guard)
- **Relationships**: Loaded from `config/settings.yaml` `risk:` block; consumed by
  `src/risk/manager.py`.
- **Defined In**: `src/risk/manager.py:40+`
- **Lifecycle**: Loaded once at process start; the F85 aggressiveness knob merges an overlay
  on top (whitelisted keys only — never the safety-gate keys) per turn.

### MarketSignalBrief
- **Purpose**: The assembled research-turn context injected into the LLM prompt.
- **Key Fields**: `movers`, `readthrough_alerts`, `imminent_earnings`, `imminent_ipos`,
  `sentiment_outliers`, `disclosed_holdings`, `degraded_sources`, `as_of`
- **Relationships**: Assembled by `src/signals/collector.py` from Mover, ReadThroughAlert,
  ImminentEarnings, ImminentIpo, SentimentOutlier records; rendered to markdown by
  `brief.to_prompt_text()`.
- **Defined In**: `src/signals/brief.py:22-43`
- **Lifecycle**: TTL-cached by `(today, horizon_days, ipo_horizon_days, held_set)`; degraded
  sections are explicitly labeled rather than silently omitted.

### EquitySnapshot / BaselineMetric / BenchmarkMetrics (F70)
- **Purpose**: The shadow-benchmark comparison of the live LLM account against deterministic
  baseline strategies.
- **Key Fields**: `EquitySnapshot`: `ts`, `strategy`, `account_masked` (never the raw account
  id), `equity`, `cash`, `position_count`. `BaselineMetric`: `strategy`, `cum_return`,
  `volatility`, `max_drawdown` (≤0), `sharpe`, `n_points`. `BenchmarkMetrics`: `ts`,
  `window_start/end`, `llm: BaselineMetric?`, `baselines: list[BaselineMetric]`,
  `alpha: dict[strategy → llm.cum_return - baseline.cum_return]`
- **Relationships**: Produced by `src/benchmark/runner.py` per tick; `compute_metrics()` is
  a pure function so the durable series can be re-analyzed offline.
- **Defined In**: `src/benchmark/models.py:9-46`
- **Lifecycle**: `EquitySnapshot`s append-only per strategy JSONL; `BenchmarkMetrics`
  recomputed and persisted per run, stamped at persist time (not compute time).

### Scenario (Eval Harness)
- **Purpose**: A frozen situation + expected agent behavior for deterministic regression
  testing of the LLM PM.
- **Key Fields**: `id`, `turn_type` ("intraday"|"wake"|"eod"), `universe`, `aggressiveness`,
  `brief?`/`wake_reasons?`/`eod_outcomes?` (turn-type-specific context), `tool_fixtures`,
  `workspace_files`, `decisions_history`, `held`, `prices`, `expectation: Expectation`
- **Relationships**: Consumed by `src/evals/sandbox.py` to build an isolated workspace;
  graded by `src/evals/grading.py` after a real agent turn.
- **Defined In**: `src/evals/scenario.py:50-93`
- **Lifecycle**: Static test fixture (JSON files under `evals/scenarios/`); never mutated at
  runtime.
