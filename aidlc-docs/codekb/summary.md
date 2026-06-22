# Codebase Summary

## Business Domain

autostock is an automated equities trading system for US (NYSE/NASDAQ via Alpaca) and Korean
(KIS) markets. The core is an **LLM portfolio manager** (Claude/GPT) that reasons over the
whole book every trading day — researching equities, writing machine-readable decisions to a
journal, and letting a deterministic Python executor place bracket orders through a central
risk gate. A human operator supervises and steers the running agent in natural language via the
operator console. A classic strategy engine (technical/ML/ensemble) rides the same safety-first
core for offline research and backtesting.

## Technical Overview

- **Primary Language**: Python 3.11+
- **Framework**: Pydantic v2 (models/settings), APScheduler 3.x (scheduling), loguru (logging)
- **Architecture Style**: Modular monolith — layered package structure, single process entrypoint
- **Build System**: hatchling (PEP 517), pip / `pip install -e .[dev]`
- **LLM Integration**: Anthropic Claude (claude-sonnet-4-6 / claude-opus), OpenAI GPT-4o; invoked via claude CLI (headless) or API key
- **Frontend**: TypeScript TUI operator console (Bun/opencode fork) communicating via file-drop channel

## Key Components

| Component | Type | Purpose |
|---|---|---|
| `main.py` | app | CLI mode dispatcher (backtest / paper / live / agent) |
| `src/core/` | shared | Pydantic domain models, enums, exceptions — no upward deps |
| `src/agent/` | app | LLM PM orchestrator, decision executor, journal, steering, self-learning |
| `src/risk/` | shared | RiskManager — the single order gate; all paths go through here |
| `src/execution/` | shared | BaseBroker + Alpaca / AccountFarm / KIS / Simulated implementations |
| `src/data/` | shared | BaseDataProvider + Alpaca / yfinance / KIS / news providers |
| `src/signals/` | shared | Research-turn signal assembly (movers, earnings, sentiment, holdings) |
| `src/strategy/` | shared | Technical / ensemble / LLM / ML strategies + registry |
| `src/backtest/` | app | Vectorised backtest engine + metrics + optimizer |
| `src/benchmark/` | app | F70 shadow baselines — deterministic strategies on sandbox accounts |
| `src/monitoring/` | shared | Health dimensions + alert publisher |
| `src/early_session/` | app | F82 early-session surge/pattern capture |
| `src/surge/` | shared | EOD surge/dive detector |
| `src/universe/` | shared | Tradeable symbol pool builder (US S&P 100, KR top-N) |
| `src/evals/` | test | LLM evaluation harness (promptfoo + custom grading) |
| `operator-console/` | frontend | TypeScript TUI for human steering (opencode fork) |
| `config/` | infra | Pydantic Settings, settings.yaml, strategies.yaml, prompt files |

## Current State

- **Total Packages**: 20+ Python sub-packages, 1 TypeScript package
- **Total Source Files**: ~150 Python source files, ~20 TypeScript files
- **Test Coverage**: Good — pytest suite covering all major subsystems; hypothesis PBT on signals
- **Last Significant Change**: F86 mobile dashboard data endpoints; F85 aggressiveness overlay; F82 intraday feature auto-collection
