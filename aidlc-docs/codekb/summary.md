# Codebase Summary

## Business Domain

Autostock is an automated equities trading platform targeting US markets (NYSE/NASDAQ via Alpaca) and Korean markets (KIS — 한국투자증권). It runs pluggable trading strategies and an agentic LLM "portfolio manager" against live brokers and a simulated broker for backtesting. It covers the full pipeline: market data → signal/strategy → risk gate → order execution → telemetry, journaling, and EOD self-review (self-learning lessons). The system is safety-first: shorting is off by default, position sizing is risk-budget driven, and a deterministic RiskManager gates every order before it reaches the broker.

## Technical Overview

- **Primary Language**: Python 3.11+
- **Framework**: Pydantic v2 (models + settings), Loguru (structured logging), APScheduler (market-time scheduling); no web framework — CLI/daemon app
- **Architecture Style**: Modular monolith with two distinct orchestration paths (strategy engine + agent loop) over a shared domain core; pluggable provider pattern throughout (broker, data, strategy)
- **Build System**: hatchling / pyproject.toml (PEP 517); Bun/Node for the TypeScript operator console

## Key Components

| Component | Type | Purpose |
|---|---|---|
| `main.py` | app | CLI dispatcher — backtest / paper / live / agent modes |
| `src/agent/` | app | Agentic LLM PM loop: orchestrator, session (claude CLI), executor, steering, telemetry, self-review |
| `src/trading/` | app | Strategy-driven TradingEngine + mode dispatch (agent / realtime / batch) |
| `src/strategy/` | shared | Pluggable strategies: technical (4), ML (RF, LSTM), LLM (Claude/OpenAI), ensemble |
| `src/risk/` | shared | RiskManager — single gate from signal/decision to Order; circuit breaker, bracket validation, short rules |
| `src/execution/` | shared | BaseBroker abstraction + Alpaca Trading, Alpaca Broker API, KIS, SimulatedBroker |
| `src/data/` | shared | BaseDataProvider + Alpaca Data, yfinance (fallback), KIS, News providers |
| `src/core/` | shared | Pydantic domain models, enums, exceptions — depended on by all, depends on nothing |
| `src/signals/` | app | Research-turn signal assembly (F61): movers, peer read-through, Finnhub earnings |
| `src/agent/steering/` | shared | Human-in-the-loop: file-drop IPC, CommandBus (NFR-2), OrderGate |
| `src/monitoring/` | shared | Health checkers (account, broker, LLM, process, disk, risk) + alert dispatch |
| `src/backtest/` | app | Vectorised bar-by-bar backtest engine + metrics + parameter optimizer |
| `src/surge/` | app | EOD surge/dive detector — extreme post-close movers |
| `src/early_session/` | app | Pre/early-market rapid-move detection (first 60 min) |
| `src/universe/` | shared | Trading universe resolver — US S&P100 / KR market-cap |
| `operator-console/` | app | TypeScript human-steering TUI (system-tray, daemon control, file-drop channel) |
| `config/` | infra | config.py (Pydantic Settings), settings.yaml, strategies.yaml |
| `.github/workflows/` | infra | CodeKB CI refresh (cooldown 4h + major-change 3% override) |

## Current State

- **Total Packages**: 16 major Python modules + TypeScript operator console
- **Total Source Files**: 169 Python source files + ~90 test files
- **Primary Markets**: US equities (Alpaca paper/live); Korean equities (KIS paper; live pending)
- **Storage**: File-based — JSONL logs, journal files, file-drop IPC; no relational/NoSQL database
- **Last Significant Change**: R7 — BrokerApiBroker side/TIF fix (short-cover bug + fail-closed TIF); R8–R13 track registrations; prior: F68 self-learning stack cleanup; M1 CodeKB CI cooldown; F60 shorting master switch; F61 market-signal brief; F3 intraday event-driven wakes
