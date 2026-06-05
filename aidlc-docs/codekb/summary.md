# Codebase Summary

## Business Domain
Autostock is an automated equities trading framework. It runs pluggable trading
strategies and an agentic LLM "portfolio manager" against live brokers (Alpaca for
US markets, KIS for Korean markets) and a simulated broker for backtesting. It covers
the full pipeline: market data → signal/strategy → risk gate → order execution →
telemetry, journaling, and EOD self-review (self-learning lessons).

## Technical Overview
- **Primary Language**: Python (>= 3.11)
- **Framework**: Pydantic v2 domain models; APScheduler for market-time scheduling; no web framework (CLI/daemon app)
- **Architecture Style**: Modular monolith with a strict layered core; two orchestration paths (strategy engine + agent loop) over a shared domain core
- **Build System**: hatchling (`pyproject.toml`)

## Key Components
| Component | Type | Purpose |
|---|---|---|
| `src/core/` | shared | Pydantic domain models, enums, exceptions; depends on nothing |
| `src/trading/` | app | `TradingEngine` (per-symbol cycle) + mode dispatch (agent/realtime/batch) |
| `src/agent/` | app | Agentic LLM portfolio manager: orchestrator, session, journal, executor, telemetry, self-review |
| `src/strategy/` | app | `BaseStrategy` registry: technical (4), ml (4), llm (5), ensemble (2) |
| `src/risk/` | app | `RiskManager` — single gate from signal/decision to `Order` |
| `src/execution/` | app | `BaseBroker` abstraction + Alpaca / KIS / Simulated brokers |
| `src/data/` | app | Data providers: Alpaca, yfinance, KIS, news |
| `src/signals/` | app | Market-signals research turn: movers, peer-map, Finnhub earnings |
| `src/backtest/` | app | Replays bars through the same RiskManager + strategies |
| `src/universe/`, `src/surge/`, `src/early_session/`, `src/monitoring/` | app | Universe selection, surge detection, early-session handling, health monitoring |

## Current State
- **Primary markets**: US equities (Alpaca); Korean equities supported via KIS broker/data (multi-broker)
- **Storage**: file-based — `workspace/` journal (markdown theses + append-only `decisions.jsonl`) + JSONL telemetry logs; no database
- **Last Significant Change**: self-learning stack (lesson attribution, hybrid recall, charter-bounded prompt self-rewrite) — tracks F64/F65/F66/F67/F68
- **Snapshot**: HEAD `58ca6a7` (2026-06-06). This is the bootstrap seed; CI refreshes it on each push to `main`.
