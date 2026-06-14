# Integration Map

## External APIs

| API | Purpose | Connection | Auth | Criticality |
|---|---|---|---|---|
| Alpaca Trading API | US equities order execution, portfolio state, account info (paper + live) | REST (`alpaca-py>=0.21`) | `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` (env) | High |
| Alpaca Broker API | Sandbox account farm creation and funding | REST (`alpaca-py`) | `BROKER_API_KEY` + `BROKER_SECRET_KEY` (env) | Medium |
| Alpaca Data API | US equities historical bars, latest quotes, news | REST + WebSocket (`alpaca-py`) | Same keys as Trading API | High |
| KIS OpenAPI (`python-kis` 2.1.6, import `pykis`) | Korean equities paper broker + market data | REST | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` (env) | High (KR mode) |
| local `claude` CLI (`claude -p`) | Agent brain — agentic portfolio manager (AgentSession) | Subprocess | OAuth subscription (`.claude/` dir on host) | High (agent mode) |
| Anthropic SDK (`anthropic>=0.18`) | LLM strategy signal generation (`src/strategy/llm/`) | REST | `ANTHROPIC_API_KEY` (env) | Medium |
| OpenAI API (`openai>=1.12`) | Alternate LLM strategy | REST | `OPENAI_API_KEY` (env) | Low (optional) |
| Finnhub — earnings calendar | Earnings calendar for signal collection (F61) | REST (`requests`) | `FINNHUB_API_KEY` (env) | Medium |
| Finnhub — IPO calendar | Imminent US IPO/catalyst awareness channel (F78); NOT universe-filtered | REST (`requests`, `/calendar/ipo`) | `FINNHUB_API_KEY` (env) | Low (best-effort) |
| Yahoo Finance (`yfinance>=0.2.30`) | Fallback / secondary market data + news | HTTP scrape | None (public) | Low (fallback) |
| StockTwits API | Retail sentiment — author self-labels (Bullish/Bearish) per symbol; hourly sweep with z-score baseline deviation detection (F77) | REST (`src/signals/sources/stocktwits.py`, unauthenticated ~200 req/hr) | None (unauthenticated) | Low (best-effort) |

## Databases & Data Stores

| Store | Type | Purpose | Access Pattern |
|---|---|---|---|
| `decisions.jsonl` | JSONL file (append-only) | Agent brain → body hand-off; LLM decisions consumed by executor | Append (orchestrator) + cursor-based read (executor) |
| `execution_log.jsonl` | JSONL file | Decision → fill audit ledger; quality metrics source | Append write |
| `turn_log.jsonl` | JSONL file | Per-turn metadata: cost, duration, decisions | Append write |
| `trades_log.jsonl` | JSONL file | Closed round-trip P&L tracking | Append write |
| `equity_log.jsonl` | JSONL file | Portfolio equity curve vs benchmark | Append write |
| `lessons.jsonl` | JSONL file | EOD self-review → learned lessons (self-learning) | Append write; recall read |
| `steering/*.jsonl` | JSONL files | Human console commands (file-drop IPC); responses | Single-writer drop (console) + daemon poll |
| `monitor.json` | JSON file | Live daemon state snapshot (positions, turn status, run state) | Overwrite on each state change |
| `surge/` store | JSONL files | EOD extreme-mover events for agent EOD analysis | Append write |
| `early_session/` | JSONL + index files | Pre-market rapid-move events (first 60 min of session) | Append write + index read |
| `data/cache/` | File cache (TTL-bounded) | Intraday bar cache; prevents redundant provider calls | Read-write with TTL expiry |
| `quality/` | JSONL files | Per-decision quality metric snapshots (F24) | Append write |
| `config/universe/*.json` | JSON files | Cached trading universe snapshots (US S&P100 / KR market-cap) | Read at startup; occasional rebuild |
| (no database) | — | All persistence is file-based; no relational/NoSQL DB | — |

## Message Queues & Events

| Queue/Topic | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| `decisions.jsonl` | Append-only file (cursor-based) | AgentTradingLoop (brain) | DecisionExecutor (body) | Durable hand-off of trade decisions; idempotent via cursor file |
| `steering/` file-drop channel | Directory of JSONL files | Operator console (TypeScript) | SteeringRuntime daemon | Human commands: lock symbol, approve/reject order, place order, adjust stop |
| Alpaca WebSocket stream | WebSocket (`alpaca-py`) | Alpaca servers | RealtimeTradingMode | Real-time bar and trade events (realtime mode only) |
| APScheduler job queue | In-process (`apscheduler>=3.10`) | TradingScheduler | Trading modes (batch/agent) | Interval ticks + US-market-cron turns (pre-market/intraday/EOD) |
| In-process CommandBus queue | Python `queue.Queue` | SteeringRuntime, snapshot workers | Single CommandBus worker | Serialised broker operations (NFR-2) |

## Notes

- **KIS specifics**: `python-kis` 2.1.6 (`pykis`) has no `stop` param; 모의투자 (paper) does not support stop-limit (`ORD_DVSN=22`) — live-only. KIS live trading is pending.
- **BrokerApiBroker (R7)**: `BrokerApiBroker` shares all request-building / fill-polling / position-mapping logic with `AlpacaBroker` via `AlpacaShapedBroker`. R7 fixed the short-cover order side mapping (was incorrectly sending `sell` instead of `buy_to_cover`) and tightened TIF handling to fail-closed (unsupported TIF raises, not silently downgrades).
- **Auth model**: All external credentials loaded from environment variables / `.env`; no secrets in repo; `AUTOSTOCK_ENV_FILE` allows test harness to load a separate `.env.test`.
- **Signal sources**: movers/news via Alpaca Data API (primary) + yfinance (fallback); earnings via Finnhub; IPO calendar via Finnhub (F78 — awareness-only, not universe-filtered); retail sentiment via StockTwits (unauthenticated, hourly sweep, baseline z-score, F77); toggleable per `settings.yaml` `signals.sources`, `signals.sentiment`, and `signals.ipo_provider` sections.
- **F78 IPO awareness (important distinction)**: IPOs are NOT filtered to the trading universe — the whole point is to surface upcoming names NOT yet in the universe. Rows are ranked by estimated value (largest first, None last), then capped at `max_ipos` (default 8). Withdrawn IPOs are always dropped. `in_universe` and `is_held` are tags, not filters.
- **Extended hours / OCO**: OCO orders do not set `extended_hours=True` — Alpaca DAY+LIMIT restriction makes extended-hours OCOs unreliable.
- **Claude CLI auth**: Agent mode requires the `claude` CLI installed and authenticated on the host (OAuth subscription token at `~/.claude/`). CI uses `CLAUDE_CODE_OAUTH_TOKEN` secret.
