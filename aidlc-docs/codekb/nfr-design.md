# NFR Design

## Resilience

| Pattern | Implementation | Location |
|---|---|---|
| Idempotent journal consumption | Cursor file tracks last-consumed decision index; atomic `os.replace()` write; safe across restarts | `src/agent/executor.py` |
| Exchange-resting protection | BRACKET/OCO legs rest at the broker (not only polled), survive process restarts | `src/risk/manager.py`, `src/agent/executor.py` |
| Circuit breaker / expiry / pool checks | Guards applied before routing agent decisions to risk/broker | `src/agent/executor.py` |
| Fail-honest collectors | Signal/data collectors surface per-source failures rather than fabricating or blocking | `src/signals/`, `src/data/providers/` |
| Polled stop/take-profit (legacy mode) | Engine polls exits when not in bracket mode | `src/trading/engine.py`, `src/risk/exits.py` |
| Event-driven intraday wakes | Wake detector (5s cadence, cache-only) fires on fills/abnormal moves/news diff without blocking the scheduler thread | `src/agent/intraday/wake.py`, `src/agent/intraday/abnormal.py` |
| Single turn lock | All LLM turns serialised by `TurnCoordinator.turn_lock`; human reconcile waits at most one wake turn | `src/agent/steering/turns.py` |
| Session token refresh | KIS session token refreshed on expiry via `SessionTimeoutWrapper` | `src/execution/brokers/session_timeout.py` |
| Turn timeout enforcement | AgentSession kills `claude -p` subprocess after `agent.turn_timeout` (default 600s) | `src/agent/session.py` |
| Atomic JSONL writes | `steering/jsonl.py` uses temp-file + `os.replace()` for all JSONL line appends | `src/agent/steering/jsonl.py` |
| Efficacy-cached singleton | `_efficacy_cached: (date, outcomes)` atomic tuple prevents redundant LLM retrospective calls within a day | `src/agent/orchestrator.py` |
| Mandatory short stop | A SELL_SHORT with no resolvable stop is rejected fail-closed (not just a polled backup) | `src/risk/manager.py` |
| Background intraday collection (F82) | Gap-backfill + EOD append run in a daemon thread; any per-symbol failure is isolated and logged; the agent loop is never blocked | `src/data/intraday/auto.py`, `src/trading/modes/agent.py` |
| Parquet upsert idempotency (F80/F82) | `IntradayFeatureStore.upsert()` deduplicates by `(date, symbol)` — re-running the same day's collection overwrites, never duplicates | `src/data/intraday/store.py` |
| F82 provider fallback | If Alpaca is unavailable, yfinance degrades gracefully to ~60d of backfill without crashing; store starts from what's available | `src/data/intraday/auto.py`, `src/data/intraday/collector.py` |

## Scalability

| Pattern | Implementation | Location |
|---|---|---|
| Multi-agent parallelism | `multi_agent.mode = parallel` spawns N sub-agents concurrently on the same research turn | `src/agent/orchestrator.py` |
| Per-symbol cycle | `TradingEngine.run_cycle()` iterates universe; `run_cycle_for_symbol()` for realtime | `src/trading/engine.py` |
| Intraday bar cache | TTL-bounded in-memory bar cache prevents redundant provider calls within cadence window | `src/data/intraday_store.py` |
| Batch interval tuning | `BatchTradingMode` interval configurable (default 15 min); tune to data provider rate limits | `src/trading/modes/batch.py` |
| Strategy precompute | Strategies implementing `supports_precompute()` can batch-compute indicators across universe | `src/strategy/base.py` |
| Concurrent health checks | `CheckerDispatcher` runs health dimension checks in parallel threads | `src/monitoring/health/checker.py` |
| Universe caching | US/KR universe cached to JSON; rebuilt only when cache is stale | `src/universe/`, `config/universe/` |
| Market-time scheduling | APScheduler interval + US-market cron avoids unnecessary ticks during off-hours | `src/trading/scheduler.py` |
| Signal TTL cache | SignalCollector TTL cache (`cache_ttl_seconds=300`) prevents duplicate fetch between push (prompt) and pull (tool) paths | `src/signals/collector.py` |
| StockTwits rate limiting | Hourly sweep rate-limited to `hourly_budget` (150 req/hr) with `request_gap_s` (0.5s) pacing | `src/signals/sentiment_sweep.py` |
| Parquet columnar store (F80) | Parquet compresses numeric intraday feature sets far better than CSV; pyarrow-backed for efficient columnar reads | `src/data/intraday/store.py` |

## Security

| Pattern | Implementation | Location |
|---|---|---|
| Steering channel token auth | File-drop commands include a shared-secret token; SteeringRuntime rejects unsigned commands | `src/agent/steering/security.py`, `src/agent/steering/channel.py` |
| Non-root container runtime | Dockerfile runs as host UID; HOME=/tmp; `/tmp/.claude` is world-writable (chmod 1777) | `Dockerfile.verify`, `docker-compose.verify.yml` |
| Secret scan at commit | gitleaks pre-commit hook scans for API keys before any commit | `.pre-commit-config.yaml` |
| Test account isolation | `AUTOSTOCK_ENV_FILE=/app/.env.test` in CI forces a separate paper account; live keys never loaded in tests | `docker-compose.verify.yml`, `config/config.py` |
| Env-file indirection | Broker/LLM keys loaded from `.env` via `pydantic-settings`; path overridable via env var | `config/config.py` |
| Shorting off by default | `shorting_enabled: false` in `settings.yaml` ships; live shorts require explicit opt-in | `config/settings.yaml`, `src/risk/manager.py` |
| Paper/live key separation | Distinct paper vs live API keys for Alpaca and KIS; paper mode enforced by `broker.paper = true` | `src/execution/brokers/` |
| Fail-closed TIF enforcement | Unsupported TIF values raise instead of silently downgrading (R7) | `src/risk/manager.py`, brokers |

## Observability

| Pattern | Implementation | Location |
|---|---|---|
| Structured logging | Loguru with configurable log level; JSON-compatible output | `src/monitoring/logger.py` |
| Health check dimensions | Modular `BaseChecker` + `CheckerDispatcher`; checkers for account, broker, data, LLM, process, disk, risk, config, logs | `src/monitoring/health/` |
| Health CLI | `scripts/health.py` runs all checkers; Rich-formatted diagnostic report | `scripts/health.py` |
| Alert dispatch | Slack and/or Telegram webhook alerts on health failures | `src/monitoring/alerts.py` |
| Live monitor snapshot | `SteeringRuntime` publishes `monitor.json` on every state change; console TUI reads it | `src/agent/steering/runtime.py` |
| Decision audit ledger | `execution_log.jsonl` records every decision → order → fill (F24) | `src/agent/executor.py` |
| Turn log | `turn_log.jsonl` records per-turn metadata (tokens, duration, decisions) | `src/agent/logs/turn.py` |
| Equity curve log | `equity_log.jsonl` persists portfolio equity after each turn vs benchmark | `src/agent/logs/equity.py` |
| Trades log | `trades_log.jsonl` records closed round-trip P&L | `src/agent/logs/trades.py` |
| Quality metrics | `src/agent/quality/` computes win rate, Sharpe, fill accuracy per decision/prompt version | `src/agent/quality/` |
| Agent trace CLI | `scripts/agent_trace.py` reads reasoning traces for transparency (F65) | `scripts/agent_trace.py` |
| Portfolio dashboard | `scripts/status.py` Rich-formatted portfolio state and round-trip P&L | `scripts/status.py` |

## Known Structural Debt

- **S-2**: `RiskManager` is dual-mode toggled by `use_bracket_orders` — legacy market-order + polled exits vs resting BRACKET/OCO. The two modes diverge in behavior.
- **S-3**: Some `src/` modules reach into the config singleton directly (layer violation vs injection through `main.py`).
- **LLM auto-improvement**: prompt auto-improvement loop does not automatically re-backtest with the new prompt; manual re-run needed.
- **KIS live**: KIS live trading is pending; paper (모의투자) does not support stop-limit (`ORD_DVSN=22`).
