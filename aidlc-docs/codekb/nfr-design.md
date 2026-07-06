# NFR Design

## Resilience

| Pattern | Implementation | Location |
|---|---|---|
| Torn-read-safe append | `read_complete_lines` consumes only newline-terminated lines and persists a byte cursor (`ByteCursor`); a truncated/rotated file resets the cursor rather than erroring | `src/core/jsonl.py` |
| Atomic in-place rewrite | Write to a unique temp file (pid+uuid) in the same directory, then `os.replace` — readers never observe a torn write | `src/core/jsonl.py` (`atomic_write_text`), used for `.executor_state.json`, position theses (post-F76), `steering/snapshot.json`, trigger specs |
| Stat-stable read (non-atomic writer) | Console reads a file between two `stat()` snapshots and retries (max 5) if size/mtime changed mid-read, to tolerate the agent's non-atomic `claude` CLI Write tool | `operator-console/src/filedrop.ts` (`readThesis`, F76) |
| Idempotent decision execution | Byte cursor + terminal-index set in `.executor_state.json`; terminal indices are never reprocessed even across a crash/restart | `src/agent/executor.py` |
| Idempotent fills | Wake detection keys on the broker's fill/activity id — one wake per `fill_id` | `src/agent/intraday/records.py` (`FillEvent`) |
| Idempotent steering commands | Day-scoped persisted processed-id set dedupes replayed/duplicated commands | `src/agent/steering/channel.py` |
| Event coalescing with bounded loss | Intraday wake events are buffered and fired as one turn; if the turn times out, buffered events are dropped (safety over data loss) rather than retried indefinitely | `src/agent/intraday/wake.py` |
| Off-hours command queuing | Human trade commands issued while the market is closed are parked in `pending_human_trades.jsonl` and drained at the next open | `src/agent/trading/modes/agent.py` / steering runtime |
| HTTP timeout bounds (F14) | Explicit connect/read timeouts installed on both Alpaca clients (TradingClient, StockHistoricalDataClient) and the KIS REST client, so a stalled socket can never wedge the daemon's scheduler thread | `src/execution/brokers/alpaca_broker.py`, `src/execution/brokers/kis/rest.py` |
| Rate limiting / throttling | KIS REST client serializes requests to a configurable per-second cap; StockTwits sweep enforces an hourly request budget and aborts the tick on a `RateLimited` exception | `src/execution/brokers/kis/rest.py`, `src/signals/sources/stocktwits.py` |
| Bounded-concurrency price fetch | Latest-price fetch across a universe uses a fixed 8-worker thread pool; one symbol's failure yields `{symbol: None}` without affecting the rest | `src/data/prices.py` |
| Cache-only scheduler reads | The 5s `WakeDetector` tick reads only cached bars/prices, never a synchronous broker fetch, so a slow broker call can never delay the daemon's core loop | `src/agent/intraday/wake.py`, `bars.py` |
| Health-check isolation | Each dimension checker (broker/risk/account/...) runs independently in a thread pool via `CheckerDispatcher`; one checker's exception degrades only its own dimension, never the whole report | `src/monitoring/health/checker.py` |
| Benchmark baseline isolation | Each shadow-baseline strategy runs its own `TradingEngine`; one baseline's exception is caught per-tick and never breaks the others or the live agent loop | `src/benchmark/runner.py` |
| Daemon health/wedge detection | The console launcher watches `snapshot.json`'s `published_at` for staleness (45s window); if wedged, it waits with patience for slow LLM turns, then auto-restarts the daemon once | `operator-console/launcher/daemon.ts` |

## Scalability

| Pattern | Implementation | Location |
|---|---|---|
| Backtest fast-path precompute | Strategies that support `supports_precompute()` and don't need dynamic per-bar selection get O(1) indicator lookups instead of an O(n²) per-bar recompute/copy | `src/backtest/engine.py` |
| Parallel parameter search | Grid-search parameter optimization runs each parameter combination in a separate process via `ProcessPoolExecutor`, isolating strategy state per worker | `src/backtest/optimizer.py` |
| Multi-instance production isolation | `COMPOSE_PROJECT_NAME=autostock-<name>` namespaces containers/volumes/networks so N daemon instances run concurrently on distinct accounts/workspaces without collision; shared verify image and `node_modules` volumes avoid per-instance rebuild/reinstall cost | `docker-compose.prod.yml`, `scripts/prod-run.sh` |
| Signal brief caching | Research-turn brief is TTL-cached by `(today, horizon_days, ipo_horizon_days, held_set)`; sentiment outliers additionally cached 300s; news cached 15 min per symbol | `src/signals/collector.py`, `src/signals/sentiment.py`, `src/data/providers/news_provider.py` |
| Universe snapshot caching | The tradeable-symbol universe is cached with a 1-day TTL and an atomic on-disk snapshot, avoiding a Wikipedia/KIS re-fetch on every process restart | `src/universe/base.py` |
| Health-check parallelism | `CheckerDispatcher` runs all dimension checks concurrently (default 6 workers) rather than sequentially | `src/monitoring/health/checker.py` |

## Security

| Pattern | Implementation | Location |
|---|---|---|
| Layered defense-in-depth (console) | (1) side-effect tools compile-time-removed under lockdown, (2) default-deny permission profile, (3) opencode's core MCP auto-gating (`ask` before every mutating tool), (4) HMAC token validation on every steering command, (5) WebAuthn passkey gate for remote mutating commands | `operator-console/cli/packages/opencode/src/tool/registry.ts`, `cli/opencode.json`, `session/tools.ts`, `src/agent/steering/`, `server/autostock/webauthn.ts` |
| Constant-time token validation | The shared steering operator token is compared in constant time to avoid timing side-channels | `src/agent/steering/channel.py` |
| Secrets never logged | Steering token, KIS appkey/appsecret, and account ids are excluded from all logs/events; `SteeringCommand.redacted()` strips the token before serialization; benchmark equity snapshots mask account ids (`account_masked`) | `src/agent/steering/records.py`, `src/benchmark/models.py` |
| Remote-vs-local trust boundary | The console classifies a request as in-process / host-local-loopback / remote; only remote mutating requests require a WebAuthn passkey assertion — host access is the trust boundary | `operator-console/cli/packages/opencode/src/server/autostock/webauthn.ts` |
| Symbol/input validation | StockTwits symbol input validated against a strict regex before URL construction; structured order args validated with zod (console) then Pydantic `extra="forbid"` (daemon) | `src/signals/sources/stocktwits.py`, `operator-console/src/mcp-server.ts` |
| Secret scanning in CI/pre-commit | gitleaks runs as a pre-commit hook with an explicit allowlist for `.env.example` templates and test fixtures | `.pre-commit-config.yaml`, `.gitleaks.toml` |
| Fail-closed provider routing | An unrecognized `broker.provider`/`data.provider` raises loudly rather than silently falling back to a default (the class of bug F92/F94 fixed) | `src/execution/brokers/factory.py` |
| Non-root container runtime (F27) | Production/verify containers run as the host's `${DOCKER_UID}:${DOCKER_GID}`, so bind-mount writes are host-owned from the start (no root-owned artifacts, no `sudo` needed for worktree cleanup) | `docker-compose.prod.yml`, `docker-compose.verify.yml`, `scripts/verify-run.sh` |
| Prod-safety preflight (F10) | The verify harness refuses to run unless `AUTOSTOCK_ENV_FILE` is set and exists, and refuses if a real `/app/.env` differs from `.env.test` — preventing an accidental prod-account test run | `scripts/verify.sh` |
| Agent lockdown (F26) | `AUTOSTOCK_LOCKDOWN=on` removes all write/exec-capable tools from the agent's toolset entirely (not just permission-gated) in production and verify-attach; an optional `AUTOSTOCK_SUPERVISOR=on` widens read-only access to the whole repo (excluding secrets/logs/.git) for human debugging sessions | `docker-compose.prod.yml`, `operator-console/launcher/config.ts` |

## Observability

| Pattern | Implementation | Location |
|---|---|---|
| Structured health reporting | `HealthReport` aggregates per-dimension `CheckResult`s with severity ordering (OK < SKIPPED < WARNING < ERROR < CRITICAL) and maps to a shell exit code for CI/cron use | `src/monitoring/health/report.py` |
| Live account/portfolio snapshot | The daemon publishes an atomic `steering/snapshot.json` on every cycle (account, positions, orders, pending approvals, health, agent activity) consumed by the console sidebar and the mobile dashboard | `src/agent/steering/` publisher, `operator-console/cli/.../autostock/dashboard-read.ts` |
| Turn/decision audit trail | Every agent turn is logged under `workspace/turns/<TURN_ID>/` (research prompt, intraday brief, etc.) alongside `turns.jsonl` metadata, enabling `/agent-trace` and `/why` console introspection | `src/agent/logs/turn.py`, console `steer_read` tools |
| Shadow-benchmark comparison | Continuous LLM-vs-deterministic-baseline equity comparison (F70) gives a standing signal on whether the LLM PM is adding value over simple strategies | `src/benchmark/` |
| Degraded-source visibility | Signal collection surfaces exactly which research sources failed (`degraded_sources`) directly in the LLM's prompt context, rather than silently omitting sections | `src/signals/collector.py`, `brief.py` |
