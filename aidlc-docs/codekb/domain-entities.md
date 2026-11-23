# Domain Entities

## Entity Catalog

### Bar
- **Purpose**: A single OHLCV candle — the basic market-data unit consumed by strategies,
  the backtester, and signal detectors.
- **Key Fields**: `timestamp: datetime`, `open/high/low/close: float`, `volume: float`
- **Relationships**: Aggregated into DataFrames by `BaseDataProvider`; consumed by
  `BaseStrategy`, `BacktestEngine`, `SignalDetector` (early session), `SurgeDetector`.
- **Defined In**: `src/core/models.py:11-19`
- **Lifecycle**: Fetched fresh per cycle/turn from a data provider; never persisted long-term
  except in the early-session buffer and the intraday Parquet feature store.

### TradeSignal
- **Purpose**: The output of a strategy — a proposed action with confidence, consumed by
  `RiskManager`.
- **Key Fields**: `symbol`, `signal: Signal` (BUY/SELL/HOLD/SELL_SHORT/BUY_TO_COVER),
  `confidence: [0,1]` (default 0.5), `sell_pct: [0,1]` (default 1.0), `strategy_name`,
  `timestamp`, `metadata: dict` (carries `key_levels`/`atr` for bracket construction)
- **Relationships**: Produced by `BaseStrategy` implementations; consumed by
  `RiskManager.evaluate_signal()`.
- **Defined In**: `src/core/models.py:22-29`
- **Lifecycle**: Ephemeral, generated per cycle, immediately converted to an `Order` or
  discarded (HOLD).

### Order
- **Purpose**: A directive to a broker — the sole output of the risk gate before execution.
- **Key Fields**: `symbol`, `side: OrderSide`, `qty`, `order_type` (market/limit/stop/
  stop_limit/trailing_stop, default market), `limit_price?`, `stop_price?`, `time_in_force`
  (default "day"), `order_class` (simple/bracket/oco/oto, default simple), `take_profit_price?`,
  `stop_loss_price?`, `trail_price?`/`trail_percent?` (exactly one, trailing_stop only),
  `extended_hours` (default False), `client_order_id?`
- **Relationships**: Produced by `RiskManager`; consumed by `BaseBroker.submit_order()`.
- **Defined In**: `src/core/models.py:32-127`
- **Lifecycle**: Validated at construction (`@model_validator` `_check_bracket_legs` enforces
  bracket/OCO leg geometry — short positions have inverted stop/target ordering vs. long, and
  a market-anchored bracket's legs must still be mutually consistent even with no entry
  reference — plus the trailing-stop exactly-one-of-price/percent rule); submitted once, never
  mutated in place.

### FilledOrder
- **Purpose**: A broker's confirmation that an order executed.
- **Key Fields**: `order_id`, `symbol`, `side`, `qty`, `filled_price`, `filled_at: datetime`,
  `commission` (default 0.0)
- **Relationships**: Returned by `BaseBroker.submit_order()`/`close_position()`; feeds
  `match_round_trips()` for P&L attribution; collected into `BacktestResult.trades`.
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
  `side: PositionSide` (LONG default/SHORT), `avg_entry_price`, `current_price` (default 0.0),
  `unrealized_pnl` (default 0.0; sign convention: short P&L = cost_basis − market_value),
  `market_value` (default 0.0), `.cost_basis` (property = qty × avg_entry_price)
- **Relationships**: Held in `PortfolioState.positions`; read/written by `RiskManager`,
  `DecisionExecutor`, console account-truth readers; feeds `src/evals/returns.py` synthetic
  replay episodes.
- **Defined In**: `src/core/models.py:152-178`
- **Lifecycle**: Refreshed via `update_price()` each cycle from the broker's latest price;
  authoritative copy always lives at the broker, never independently persisted as truth.

### PortfolioState
- **Purpose**: A full account snapshot.
- **Key Fields**: `cash`, `equity` (source of truth — never recomputed from positions to
  avoid silent divergence from stale prices), `positions: dict[symbol → Position]`,
  `timestamp` (default now), `.position_count` (property)
- **Relationships**: Returned by `BaseBroker.get_portfolio_state()`; feeds `RiskManager`
  sizing/limits and the published `snapshot.json`.
- **Defined In**: `src/core/models.py:181-194`
- **Lifecycle**: Fetched fresh per cycle/turn; not stored beyond the current snapshot except
  in `equity.jsonl` (EOD append, also carries the `benchmark.SPY` mark consumed by
  `compute_performance`) and benchmark `EquitySnapshot` series.

### BacktestResult
- **Purpose**: The summary output of a classic-strategy backtest run.
- **Key Fields**: `strategy_name`, `start_date`/`end_date`, `initial_capital`/`final_capital`,
  `total_return_pct`, `sharpe_ratio` (default 0.0), `max_drawdown_pct` (default 0.0),
  `total_trades` (default 0), `win_rate` (default 0.0), `profit_factor` (default 0.0),
  `equity_curve: list[float]`, `trades: list[FilledOrder]`
- **Relationships**: Produced by `BacktestEngine`; consumed by CLI/report renderers.
- **Defined In**: `src/core/models.py:197-212`
- **Lifecycle**: Computed once per backtest run; not persisted beyond the run's output
  artifact.

### Decision
- **Purpose**: The agent's (or human's) machine-readable trading action — the append-only
  unit of the LLM PM's journal.
- **Key Fields**: `ts`, `symbol`, `action: DecisionAction` (BUY/SELL/HOLD/ADJUST_STOP/
  SELL_SHORT/BUY_TO_COVER), `turn_id?`, `source` ("agent" default|"human"), `confidence?`
  (default 0.5, nullable), `sell_pct?` (default 1.0, nullable), `limit?` (suggested entry,
  None = market), `stop?`/`target?` (suggested stop-loss/take-profit → RiskManager bracket),
  `ref_price?` (**F96**: price at decision time, stamped post-hoc by the orchestrator only for
  market entries — BUY/SELL_SHORT with `limit=None` — and consumed only by the executor's
  entry drift guard; None on legacy lines or when the price fetch fails), `thesis_ref?`,
  `valid_until?`, `reason`, `lessons_cited: list[str]` (F62 attribution), `prompt_version`
  (default "seed"), `aggressiveness` (default "balanced") + `grading_horizon_days` (default
  20, F85)
- **Relationships**: Written to `decisions.jsonl` by the agent's Claude/OpenAI session (async
  append), then post-hoc stamped (`ref_price`, `prompt_version`/`lessons_cited`) by Python via
  an atomic full-file rewrite (`restamp_decisions`); consumed one-at-a-time by
  `DecisionExecutor`, whose `_to_signal` forwards `ref_price` via `TradeSignal.metadata` so
  `RiskManager`'s entry drift guard (`entry_drift_guard_atr`) can demote a MARKET order to
  LIMIT@anchor±band when live price has drifted ≥0.5 ATR against the decision-time anchor.
- **Defined In**: `src/agent/journal.py:55-108`
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
- **Key Fields**: `lesson_id`, `date` (default today), `category` (default "other"; one of
  `entry_timing`/`exit_timing`/`risk_mgmt`/`regime`/`thesis`/`sizing`/`other`), `signal_used`,
  `outcome`, `takeaway`, `regime` (F62 tag), `sector?` (F62 tag); `times_applied` is
  **deprecated** (`repr=False`, never incremented — see `applied_counts()`/`LessonEfficacy`
  for the authoritative count, avoiding an in-place-increment race on the append-only file)
- **Relationships**: Written to `lessons.jsonl` via `Journal.append_lesson_record`;
  ranked/filtered by `src/agent/learning/recall.py` (F65) for injection into future prompts;
  aggregated into `LessonEfficacy` by `src/agent/learning/efficacy.py` (F62).
- **Defined In**: `src/agent/journal.py:36-52`
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
  `short_market_halt_threshold_pct`), `individual_stock_halt_pct` (0.10, squeeze guard),
  `entry_drift_guard_atr` (**F96**, default 0.5; 0 disables — the ATR multiple of adverse
  drift between `Decision.ref_price`/entry and live price that demotes a MARKET order to a
  LIMIT at anchor±band before it reaches the broker)
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

### NewsItem (news-freshness enrichment, F96)
- **Purpose**: A news article item surfaced to strategies/the agent; the `news()` agent tool
  (not the model itself) now annotates each item with freshness so the LLM can't treat a
  stale headline as a fresh catalyst.
- **Key Fields**: `title`, `summary`, `link`, `publisher`, `published_at: datetime?`,
  `sentiment_score?` ([-1,1]). Tool-level (non-model, computed in
  `src/agent/tools/market.py:news()`): `age_hours: float?` (injectable clock, tz-safe,
  fail-honest → None if `published_at` missing) and `priced_in_risk: "fresh"|"elevated"|None`
  (elevated once `age_hours` exceeds the freshness threshold).
- **Relationships**: Defined in `src/data/providers/news_provider.py`; produced by
  `YFinanceNewsProvider`; consumed by `MarketDataFormatter._format_news` (classic LLM
  strategy) and the agent's `news()` tool (PM agent), whose prompt rules treat `elevated`
  headlines as already-priced-in absent a fresh confirming signal (with an aggressive-posture
  exception).
- **Defined In**: `src/data/providers/news_provider.py:13-23`; freshness logic in
  `src/agent/tools/market.py:235-277`
- **Lifecycle**: Ephemeral per tool call; `age_hours`/`priced_in_risk` are computed fresh each
  invocation against the injected "now", never cached or persisted.

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

### PerformanceVsBenchmark (F97)
- **Purpose**: The "am I beating the S&P 500?" headline scorecard — a read-time join of the
  agent's EOD equity series against the SPY buy-and-hold mark already recorded alongside it,
  so an operator sees cumulative agent return, cumulative SPY return, alpha, and today's delta
  without a new durable record.
- **Key Fields** (dict shape, not a Pydantic model): `base_date`, `agent_return_pct`,
  `spy_return_pct`, `alpha_pct` (= agent − SPY), plus a today's-delta figure; returns `None`
  (fail-honest) when no `equity.jsonl` line has both a positive `equity` and a positive
  `benchmark.SPY` mark — the baseline is the first day the index mark exists, making the
  ratio independent of starting capital.
- **Relationships**: Pure core `compute_performance()` in `src/agent/logs/performance.py`
  reads `equity.jsonl` records (see `src/agent/logs/equity.py`, which already stamps
  `benchmark.SPY` per EOD line — no EOD-pipeline change needed); folded additively into
  `src/agent/steering/runtime.py`'s snapshot dict as `perf_vs_benchmark`; surfaced by
  `scripts/status.py`, the operator-console sidebar, and the mobile dashboard (F86).
- **Defined In**: `src/agent/logs/performance.py:26-80`
- **Lifecycle**: Recomputed on every snapshot/status read (no caching, no persistence);
  purely derived from the existing append-only equity log.

### ResearchProfile (model/eval reasoning axes)
- **Purpose**: An explicit, named (provider, model, reasoning effort, prompt_ref) combination
  used to pin and reproduce an LLM research-turn configuration for comparison runs — decouples
  "which model/effort/prompt was used" from the live default config so historical comparisons
  stay reproducible even as defaults change.
- **Key Fields**: `name` (`^[a-zA-Z0-9_-]+$`), `provider` ("claude_code"|"openai", default
  claude_code), `model`, `effort: ReasoningEffort` (low/medium/high/xhigh/max, default
  "high"), `prompt_ref` (default "current"; else `"baseline:<name>"` pinning a bundled
  `evals/baselines/<name>/` snapshot, or a git ref resolved via `git rev-parse`/`git show`)
- **Relationships**: Resolved by `prompt_snapshot()` into a pinned `src/agent/prompts.py`
  module + `CLAUDE.md` manual + sha256 metadata; consumed by `src/evals/compare_research.py`'s
  `MeasuredRunner` and `evals/research_profiles.json` to run the same scenario across
  multiple model/effort/prompt configurations.
- **Defined In**: `src/evals/profiles.py:19-26` (model), `profiles.py:28-58`
  (`prompt_snapshot`)
- **Lifecycle**: Static config loaded per comparison run; `extra="forbid"` rejects unknown
  keys; never mutated once loaded.

### FutureBar / OutcomePath (post-decision return evaluation)
- **Purpose**: A frozen, information-cutoff-respecting "future tape" used to score a single
  real decision's resting-exit outcome without ever letting future bars leak into the
  deciding model's sandbox — validates accounting/execution realism, not trading skill.
- **Key Fields**: `FutureBar`: `open_at`/`close_at` (both tz-aware, required), `open`/`high`/
  `low`/`close` (≥0, finite; OHLC-range-validated). `OutcomePath`: `scenario_id`, `as_of`
  (tz-aware cutoff), `kind` ("synthetic"|"historical"|"forward"), `provenance` (non-empty),
  `bars: dict[symbol → list[FutureBar]]`, `benchmark: list[FutureBar]`, `cost_bps_per_side`
  (default 10), `borrow_apr` (default 0.03), `cash_apr` (default 0), `corporate_actions`
  (must be empty — splits/dividends are explicitly unsupported by this scorer)
- **Relationships**: Validated (`@model_validator`) so every symbol's bar grid exactly
  matches the benchmark's non-overlapping, post-cutoff grid; replayed by a `_ReplayBroker`
  (extends `SimulatedBroker`, charges friction both sides, fills gapped stops at the adverse
  open) inside `src/evals/returns.py`, driving the same production `DecisionExecutor` against
  a frozen `Scenario`/`Position` book.
- **Defined In**: `src/evals/returns.py:32-74`; JSON Schema mirrored at
  `evals/outcome-path.schema.json`
- **Lifecycle**: Static evaluation fixture per episode; never mutated after construction
  (both models are `extra="forbid"`).

### Scenario (Eval Harness)
- **Purpose**: A frozen situation + expected agent behavior for deterministic regression
  testing of the LLM PM.
- **Key Fields**: `id`, `turn_type` ("intraday"|"wake"|"eod"), `universe`, `aggressiveness`,
  `brief?`/`wake_reasons?`/`eod_outcomes?` (turn-type-specific context), `tool_fixtures`,
  `workspace_files`, `decisions_history`, `held`, `prices`, `expectation: Expectation`
- **Relationships**: Consumed by `src/evals/sandbox.py` to build an isolated workspace;
  graded by `src/evals/grading.py` after a real agent turn; also the frozen book an
  `OutcomePath` episode replays against (`src/evals/returns.py`).
- **Defined In**: `src/evals/scenario.py:50-93`
- **Lifecycle**: Static test fixture (JSON files under `evals/scenarios/`, now including a
  `research/` subtree of research-turn scenarios); never mutated at runtime.

### AgentConfig / LLMConfig (provider + reasoning-effort pinning)
- **Purpose**: The config-layer entities that pin which model backend and reasoning effort
  the trading agent and the classic LLM strategy run with — now multi-provider (Claude Code
  CLI or OpenAI Responses API) with validation preventing a model/provider mismatch.
- **Key Fields**: `AgentConfig`: `provider` ("claude_code" default|"openai"), `model` (default
  "claude-sonnet-5-5"), `research_model` (default "claude-opus-5-5"), `effort:
  ReasoningEffort` (default "medium"), `research_effort` (default "high"),
  `max_output_tokens`, `turn_timeout`, `research_timeout`,
  `research_start_before_open`/`research_end_before_open`, `min_trade_notional`,
  `aggressiveness: AggressivenessLevel` (F85, fail-safe-coerced to "balanced" on unknown
  value). `LLMConfig` (classic strategy path): `provider`, `model?`, `temperature`,
  `reasoning_effort`, `max_output_tokens`, `prompt_version`, `lookback_days`, `include_news`.
  `ReasoningEffort = Literal["low","medium","high","xhigh","max"]`.
- **Relationships**: `AgentConfig._matching_provider` validator rejects a Claude-named model
  under `provider="openai"` (or a `gpt-*` model under `provider="claude_code"`); consumed by
  `src/agent/session.py`/`src/agent/openai_session.py` (session construction) and
  `src/strategy/llm/strategy.py`.
- **Defined In**: `config/config.py:19`, `config/config.py:102-111` (LLMConfig),
  `config/config.py:113-154` (AgentConfig)
- **Lifecycle**: Loaded once at process start from `config/settings.yaml` + env; immutable
  for the life of the process.

### OpenAIAgentSession (alternate agent backend)
- **Purpose**: A second `AgentSession` implementation that drives the PM agent via the OpenAI
  Responses API instead of the Claude Code CLI, sharing the same production prompts, journal,
  and executor — added so model/effort comparisons (see `ResearchProfile`) can run a real
  non-Claude backend.
- **Key Fields**: `api_key` (required unless an injected `client` is supplied — a Codex
  subscription login does not count), `model` (default "gpt-6-astra"), `effort` (default
  "high"), `timeout` (default 600.0), `max_output_tokens` (default 32768), `one_shot`,
  `read_only` (suppresses the broker/shell-capable tools), `observer`, `allow_web`
- **Relationships**: Subclasses `AgentSession` (`src/agent/session.py`); exposes journal tools
  and read-only market data via strict-schema function-calling (`_function()` helper); no
  shell or broker order tool is exposed directly to the model.
- **Defined In**: `src/agent/openai_session.py:28+`
- **Lifecycle**: Constructed per turn/session by the orchestrator when
  `AgentConfig.provider == "openai"`; not persisted.
