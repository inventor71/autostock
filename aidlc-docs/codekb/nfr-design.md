# NFR Design

## Resilience

| Pattern | Implementation | Location |
|---|---|---|
| Idempotent execution cursor | decisions.jsonl byte cursor; re-read from top on restart; dedup by turn_id | `src/agent/executor.py` |
| Exchange-held bracket orders | Stop+take-profit submitted as OCO pair at exchange; not a polling loop | `src/risk/manager.py`, `src/core/models.py:Order` |
| Fail-honest signal wiring | Signal wiring wrapped in try/except; any failure returns None (agent runs without signals) | `main.py:_make_signal_brief_provider()` |
| Fail-honest benchmark runner | Benchmark wrapped in try/except; agent loop never blocked by benchmark failure | `main.py:_maybe_start_benchmark()` |
| Atomic snapshot write | snapshot.json written via temp file + atomic rename; console never reads a torn snapshot | `src/agent/steering/jsonl.py:atomic_write_text()` |
| Session-day cache atomic swap | _efficacy_cached: tuple[date, list] single-attr assignment; cross-thread read is never torn | `src/agent/orchestrator.py` |
| Constitution compliance rollback | Self-rewrite compliance check; non-compliant guidance discarded, old version preserved | `src/agent/learning/constitution.py`, `src/agent/learning/self_rewrite.py` |
| Turn-level timeout | Per-turn turn_timeout (600s) and research_timeout (1800s) prevent hung agent turns | `config/settings.yaml`, `src/agent/session.py` |
| Off-hours order queue | Human commands during market-closed periods queued and drained at open | `src/agent/steering/state.py`, `src/agent/steering/commands.py` |
| Daily command file archive | Steering channel archives commands.jsonl at ET-midnight; prevents unbounded growth | `src/agent/steering/channel.py:daily_reset()` |
| KIS session token refresh | KIS broker auto-refreshes OAuth token before expiry | `src/execution/brokers/session_timeout.py` |

## Scalability

| Pattern | Implementation | Location |
|---|---|---|
| Multi-agent parallel research | ThreadPoolExecutor spawns N sub-agent tasks concurrently (Mode C) or sequentially (Mode B) | `src/agent/orchestrator.py` |
| Intraday feature Parquet store | Per-symbol session features stored as Parquet (columnar, efficient append/range-scan) | `src/data/intraday/store.py`, `data/intraday/<SYM>.parquet` |
| Signal scan timeout cap | Aggregate price scan capped at scan_timeout_seconds (30s) so signals never delay a turn | `src/signals/settings.py`, `src/signals/collector.py` |
| Signal price cache | cache_ttl_seconds=300 on signal scans; price.cache_seconds=3 on intraday price lookups | `src/signals/collector.py`, `src/agent/intraday/bars.py` |
| Background benchmark runner | BenchmarkRunner runs in its own thread; never in the agent critical path | `src/benchmark/runner.py` |
| Background 13F holdings refresher | Holdings refreshed in daemon background thread every refresh_hours; research/universe path reads cache | `src/signals/holdings/refresher.py` |
| Intraday backfill in background thread | Gap-backfill of Parquet features runs on daemon start without blocking the loop | `src/data/intraday/auto.py` |

## Security

| Pattern | Implementation | Location |
|---|---|---|
| HMAC token auth for steering channel | Every command carries a constant-time HMAC MAC (hmac.compare_digest). Token never written to logs/events. | `src/agent/steering/channel.py`, `src/agent/steering/security.py` |
| API keys env-only | All secrets loaded from environment / .env; not in settings.yaml or config/ | `config/config.py`, `config/settings.yaml` |
| Pre-commit gitleaks secret scan | .pre-commit-config.yaml runs gitleaks hook before every commit | `.pre-commit-config.yaml` |
| Shorting master switch off by default | risk.shorting_enabled: false; short entries fail-closed without explicit opt-in | `src/risk/manager.py`, `config/settings.yaml` |
| Universe constraint + ETB gate | Agent decisions outside approved universe filtered before execution; ETB checked on shorts | `src/agent/orchestrator.py:filter_in_universe()`, `src/execution/base.py:is_shortable()` |
| Constitution SHA pin in CI | tests/test_constitution_pin.py pins AGENT_CONSTITUTION SHA-256; any edit fails CI | `tests/test_constitution_pin.py`, `src/agent/learning/constitution.py` |
| SEC fair-access User-Agent | EDGAR requests identify the application with a real contact email per SEC fair-access policy | `config/settings.yaml:signals.disclosed_holdings.user_agent` |

## Observability

| Pattern | Implementation | Location |
|---|---|---|
| Structured loguru logging | loguru with file rotation (logs/autostock.log); INFO default, DEBUG available | `src/monitoring/logger.py:setup_logging()` |
| Health dimension report | Parallel checks across 9 dimensions (account, broker, LLM, config/env, data pipeline, logs, process, resources, risk) | `src/monitoring/health/checker.py`, `src/monitoring/health/dimensions/` |
| Operational alerts | Slack webhook + Telegram bot alert publisher; disabled by default | `src/monitoring/alerts.py` |
| Turn log (JSONL per turn) | Each agent turn emitted as a structured JSONL record with turn_id, turn_type, decisions list | `src/agent/logs/turn.py` |
| Quality metrics snapshot | Decision-level grading, aggregate P&L, win rate, Sharpe; exposed via /quality tool | `src/agent/quality/` |
| Benchmark equity tracking | Parallel LLM + deterministic baseline equity curves for head-to-head comparison | `src/benchmark/store.py`, `data/benchmark/` |
| Steering event feed | All daemon outcomes (fills, rejections, agent status) emitted to steering/events.jsonl | `src/agent/steering/channel.py` |
| Intervention record | Every human steering command and its outcome logged to workspace/interventions.jsonl | `src/agent/steering/records.py:InterventionRecord` |
| Agent trace script | scripts/agent_trace.py replays the turn log for post-session forensics | `scripts/agent_trace.py` |

## Testability

| Pattern | Implementation | Location |
|---|---|---|
| SimulatedBroker | Full in-process broker filling all orders at market price, tracking positions/fills | `src/execution/brokers/simulated_broker.py` |
| Hypothesis property-based testing | Signals module uses hypothesis for generative scenario testing | `tests/signals/test_properties.py`, `tests/signals/test_scenarios.py` |
| Eval harness | promptfoo-based + custom grading for LLM decision quality evaluation | `src/evals/`, `evals/` |
| Manual test marker | @pytest.mark.manual deselected by default — only opt-in tests call the real LLM | `pyproject.toml:pytest.ini_options.addopts` |
| Refactor baseline JSON | Speed regression baseline captured in tests/refactor/golden/baseline.json | `tests/refactor/test_speed_baseline.py` |
| Docker verification | Dockerfile.verify + docker-compose.verify.yml run the full test suite in a clean container | `Dockerfile.verify`, `docker-compose.verify.yml`, `scripts/verify.sh` |
