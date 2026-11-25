# Codebase Summary

## Business Domain

autostock is an automated equities trading system for US (NYSE/NASDAQ via Alpaca) and Korean
(KIS) markets, now extended with a read-only-first **Toss Securities (토스증권)** integration
for a Korean-brokered US-equities account. The core is an **LLM portfolio manager** (Claude,
invoked headless via the local `claude` CLI, with an OpenAI Responses API backend as a
pluggable alternative) that reasons over the whole book every trading day — researching
equities, writing machine-readable `Decision` lines to an append-only journal, and letting a
deterministic Python executor place bracket orders through a single central risk gate. A human
operator supervises and steers the running agent in natural language via a TypeScript operator
console (TUI, fork of opencode) that attaches over a file-drop channel — including from a phone
via Tailscale + WebAuthn passkeys. A classic strategy engine (technical/ML/ensemble) rides the
same safety-first core for offline research, backtesting, and shadow benchmarking against the
live LLM account.

Architecture is a strict brain/body split: the LLM (brain) proposes; a deterministic
`DecisionExecutor` (body) is the only actuator, with an idempotent cursor so restarts never
double-submit. Every order — from the agent, from a strategy signal, or from a human steering
command — passes through one `RiskManager.validate_order()` gate. Shorting ships off by
default; protective stop/take-profit legs rest at the exchange (bracket orders); a circuit
breaker halts new entries on extreme market moves; an entry-drift guard (F96) caps a momentum
market order to a bounded limit if price has run away from the decision-time anchor. The
agent's durable memory (journal, theses, lessons, equity curve) survives restarts and feeds a
bounded self-learning loop (lesson efficacy tracking, aggressiveness knob, self-authored
long-horizon triggers). A read-time performance scorecard (F97) answers "am I beating the
S&P 500" directly from the existing equity log, and a research-comparison harness
(`src/evals/compare_research.py`, `returns.py`) evaluates candidate models/prompts
(Fable, Astra/OpenAI) against the production path without ever promoting a model
automatically.

**Toss integration (F100-F105)** adds a second non-Alpaca live-broker path, deliberately scoped
narrower than Alpaca/KIS: it reads an existing `toss-stock` desktop app's auth token read-only
(never minting/refreshing its own token unless run in a standalone direct-credentials mode),
supports only MARKET/LIMIT orders with no brackets/OCO/shorting/extended-hours, and floors
fractional sell quantities to 6 decimals. Because Toss's live account can't safely host
agent-driven bracket trading yet, a parallel **quote-driven shadow simulator**
(`TossShadowBroker` + `src/evals/toss_shadow.py`) replays the real agent/executor/risk stack
against a durable local ledger seeded from the live Toss account, using real Toss orderbook
quotes for fills — giving an apples-to-apples "would the agent have traded this book" signal
without placing real Toss orders. **F105** then generalized a shared "research context" (bars,
quotes, news, account snapshot) assembly (`src/agent/intraday/context.py`) used by *both* the
normal daemon and the Toss shadow runner, with explicit fail-honest gap reporting
(`src/monitoring/research.py`) distinguishing "source timestamp" from "retrieval timestamp" so
stale data is never silently treated as current.

## Technical Overview

- **Primary Language**: Python 3.11+ (backend/daemon), TypeScript (operator console, Bun runtime)
- **Framework**: Pydantic v2 (models/settings), APScheduler 3.x (market-aware scheduling), loguru (logging)
- **Architecture Style**: Modular monolith — layered package structure, single daemon process; multi-instance production runtime via Docker Compose project namespacing
- **Build System**: hatchling (PEP 517) for Python; Bun workspace for the console (opencode fork)
- **LLM Integration**: Anthropic Claude (headless `claude -p` CLI, subscription auth) for the agent brain and console by default; a parallel `OpenAIAgentSession` (Responses API) backend drives the same prompts/journal/executor when `agent.provider=openai`; Claude/OpenAI API also supported as a pluggable strategy-engine signal source
- **Frontend**: TypeScript TUI operator console (Bun/opencode fork), plus a mobile PWA dashboard served over Tailscale with WebAuthn passkey gating for remote mutating commands

## Key Components

| Component | Type | Purpose |
|---|---|---|
| `main.py` | app | CLI mode dispatcher (backtest / paper / live / agent) + broker/strategy/data composition root |
| `src/core/` | shared | Pydantic domain models, enums, exceptions, JSONL/atomic-write primitives, market-time helpers — depends on nothing |
| `src/agent/` | app | LLM PM orchestrator (brief/entry-drift-guard anchor stamping), journal, decision executor, dual-provider session (Claude CLI / OpenAI Responses), steering, self-learning (efficacy/recall), intraday wake detection + shared `IntradayContext` (F105), self-authored triggers, performance-vs-benchmark scorecard (F97) |
| `src/risk/` | shared | RiskManager — the single order gate (sizing, brackets, circuit breaker, shorting gate, F96 entry-drift guard) |
| `src/execution/` | shared | BaseBroker + Alpaca / AccountFarm (sandbox sub-accounts) / KIS / Toss (`TossBroker`, live, read-only-by-default) / `TossShadowBroker` (quote-driven dry simulation) / Simulated implementations, provider-aware `create_broker` factory |
| `src/data/` | shared | BaseDataProvider + Alpaca / yfinance / KIS / Toss (`TossDataProvider`) providers, shared news layer (`news.py`: `FallbackNewsProvider`, `NewsResult`) and source-vs-retrieval-timestamp helpers (`freshness.py`, F105) |
| `src/signals/` | shared | Research-turn signal assembly (movers, read-through, earnings/IPO calendars, StockTwits sentiment, disclosed holdings), now stamping per-symbol `price_source_times` (F105) |
| `src/strategy/` | shared | Technical / ensemble / LLM / ML strategies + registry; `llm/client.py` modernized for adaptive-thinking Claude 5.x and OpenAI Responses `reasoning.effort` |
| `src/backtest/` | app | Vectorised look-ahead-safe backtest engine + metrics + parameter optimizer |
| `src/benchmark/` | app | F70 shadow baselines — deterministic strategies on sandbox accounts, compared against the live LLM account |
| `src/monitoring/` | shared | Health-check dimensions (broker/risk/account/llm/config_env — dual-provider and Toss-credential aware) + alert publisher + `research.py` (F105) read-only "research data gap" summary (news/quote/bar staleness, watchlist coverage, account errors) |
| `src/early_session/` | app | Early-session (09:30-10:30 ET) surge/pattern capture and dump |
| `src/surge/` | shared | EOD surge/dive detector with agent-assisted root-cause tagging |
| `src/universe/` | shared | Tradeable symbol pool builder (US S&P 100, KR top-N), theme overlays, atomic snapshot cache |
| `src/trading/` | app | TradingEngine + batch/realtime/agent execution modes; agent mode now wraps bar/watch/news/brief assembly in a shared `IntradayContext` (F105) |
| `src/evals/` + `evals/` | test | Deterministic tier-1 grading (extraction, behavior, executor replay) + promptfoo LLM eval harness + research-mode comparison (`compare_research.py`) + post-decision outcome-path return scoring (`returns.py`) + `toss_shadow.py` (agent-driven shadow-account turn runner with durable decision identity and persistent retry backoff) |
| `operator-console/` | frontend | TypeScript TUI (opencode fork) for human steering; launcher, systemd units, mobile serve/WebAuthn, warm-quote symbol panel (F95) |
| `config/` | infra | Pydantic Settings, `settings.yaml`, `strategies.yaml`, per-instance `.env.<name>`, prompt files, Toss credentials file (outside the repo, 0600) |
| `docker-compose.prod.yml` / `scripts/prod-run.sh` | infra | Multi-instance production runtime (F90) — per-account isolation, shared image/deps |

## Current State

- **Total Packages**: 20+ Python sub-packages, 1 TypeScript workspace (operator-console)
- **Total Source Files**: ~170+ Python source files, ~20+ TypeScript files
- **Test Coverage**: Good — pytest suite across all major subsystems (risk, execution, agent, signals, triggers, trading judgment, model runtime, drift guard, news freshness, performance scorecard, Toss broker/client/costs/credentials/quality/shadow, shared research context), hypothesis property-based tests, deterministic promptfoo eval harness with executor-replay grading
- **Last Significant Change**: Toss Securities broker integration (F100-F105) — a read-only-by-default live broker (`TossBroker`, MARKET/LIMIT only, no shorts/brackets/OCO/extended-hours, 6-decimal fractional-sell flooring) reusing an external `toss-stock` app's auth token, plus a durable quote-driven shadow simulator (`TossShadowBroker`/`src/evals/toss_shadow.py`) that replays the real agent/executor/risk stack against Toss orderbook quotes with crash-safe decision identity and exponential retry backoff; and a shared "research context" refresh (F105) generalizing bar/quote/news assembly (`src/agent/intraday/context.py`) across the normal daemon and the Toss shadow runner, with explicit fail-honest data-gap reporting (`src/monitoring/research.py`) and a source-timestamp-vs-retrieval-timestamp distinction (`src/data/freshness.py`) so stale data is never silently treated as fresh.
