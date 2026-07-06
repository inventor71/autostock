# Codebase Summary

## Business Domain

autostock is an automated equities trading system for US (NYSE/NASDAQ via Alpaca) and Korean
(KIS) markets. The core is an **LLM portfolio manager** (Claude, invoked headless via the
local `claude` CLI) that reasons over the whole book every trading day — researching equities,
writing machine-readable `Decision` lines to an append-only journal, and letting a
deterministic Python executor place bracket orders through a single central risk gate. A human
operator supervises and steers the running agent in natural language via a TypeScript
operator console (TUI, fork of opencode) that attaches over a file-drop channel — including
from a phone via Tailscale + WebAuthn passkeys. A classic strategy engine (technical/ML/
ensemble) rides the same safety-first core for offline research, backtesting, and shadow
benchmarking against the live LLM account.

Architecture is a strict brain/body split: the LLM (brain) proposes; a deterministic
`DecisionExecutor` (body) is the only actuator, with an idempotent cursor so restarts never
double-submit. Every order — from the agent, from a strategy signal, or from a human steering
command — passes through one `RiskManager.validate_order()` gate. Shorting ships off by
default; protective stop/take-profit legs rest at the exchange (bracket orders); a circuit
breaker halts new entries on extreme market moves. The agent's durable memory (journal,
theses, lessons, equity curve) survives restarts and feeds a bounded self-learning loop
(lesson efficacy tracking, aggressiveness knob, self-authored long-horizon triggers).

## Technical Overview

- **Primary Language**: Python 3.11+ (backend/daemon), TypeScript (operator console, Bun runtime)
- **Framework**: Pydantic v2 (models/settings), APScheduler 3.x (market-aware scheduling), loguru (logging)
- **Architecture Style**: Modular monolith — layered package structure, single daemon process; multi-instance production runtime via Docker Compose project namespacing
- **Build System**: hatchling (PEP 517) for Python; Bun workspace for the console (opencode fork)
- **LLM Integration**: Anthropic Claude (headless `claude -p` CLI, subscription auth) for the agent brain and console; Claude/OpenAI API also supported as a pluggable strategy-engine signal source
- **Frontend**: TypeScript TUI operator console (Bun/opencode fork), plus a mobile PWA dashboard served over Tailscale with WebAuthn passkey gating for remote mutating commands

## Key Components

| Component | Type | Purpose |
|---|---|---|
| `main.py` | app | CLI mode dispatcher (backtest / paper / live / agent) + broker/strategy/data composition root |
| `src/core/` | shared | Pydantic domain models, enums, exceptions, JSONL/atomic-write primitives, market-time helpers — depends on nothing |
| `src/agent/` | app | LLM PM orchestrator, journal, decision executor, session (claude CLI), steering, self-learning (efficacy/recall), intraday wake detection, self-authored triggers |
| `src/risk/` | shared | RiskManager — the single order gate (sizing, brackets, circuit breaker, shorting gate) |
| `src/execution/` | shared | BaseBroker + Alpaca / AccountFarm (sandbox sub-accounts) / KIS / Simulated implementations, provider-aware `create_broker` factory |
| `src/data/` | shared | BaseDataProvider + Alpaca / yfinance / KIS / news providers |
| `src/signals/` | shared | Research-turn signal assembly (movers, read-through, earnings/IPO calendars, StockTwits sentiment, disclosed holdings) |
| `src/strategy/` | shared | Technical / ensemble / LLM / ML strategies + registry |
| `src/backtest/` | app | Vectorised look-ahead-safe backtest engine + metrics + parameter optimizer |
| `src/benchmark/` | app | F70 shadow baselines — deterministic strategies on sandbox accounts, compared against the live LLM account |
| `src/monitoring/` | shared | Health-check dimensions (broker/risk/account/...) + alert publisher |
| `src/early_session/` | app | Early-session (09:30-10:30 ET) surge/pattern capture and dump |
| `src/surge/` | shared | EOD surge/dive detector with agent-assisted root-cause tagging |
| `src/universe/` | shared | Tradeable symbol pool builder (US S&P 100, KR top-N), theme overlays, atomic snapshot cache |
| `src/trading/` | app | TradingEngine + batch/realtime/agent execution modes |
| `src/evals/` + `evals/` | test | Deterministic tier-1 grading (extraction, behavior, executor replay) + promptfoo LLM eval harness |
| `operator-console/` | frontend | TypeScript TUI (opencode fork) for human steering; launcher, systemd units, mobile serve/WebAuthn |
| `config/` | infra | Pydantic Settings, `settings.yaml`, `strategies.yaml`, per-instance `.env.<name>`, prompt files |
| `docker-compose.prod.yml` / `scripts/prod-run.sh` | infra | Multi-instance production runtime (F90) — per-account isolation, shared image/deps |

## Current State

- **Total Packages**: 20+ Python sub-packages, 1 TypeScript workspace (operator-console)
- **Total Source Files**: ~150+ Python source files, ~20+ TypeScript files
- **Test Coverage**: Good — pytest suite across all major subsystems (risk, execution, agent, signals, triggers), hypothesis property-based tests, deterministic promptfoo eval harness with executor-replay grading
- **Last Significant Change**: Broker/account provider read-path consistency across both the Python agent CLI (F92) and the TypeScript console (F94) so multi-instance `account_farm` deployments never observe a shared/wrong sub-account; mobile execution-path route-mounting fix (F93); Docker production multi-instance runtime (F90); self-authored long-horizon triggers (F88); sentiment sweep clock and thesis torn-read hardening (F91/F76)
