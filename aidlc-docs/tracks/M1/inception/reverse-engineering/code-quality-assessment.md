# Code Quality Assessment & Structural Review

**Date**: 2026-05-28 · **Scope**: `src/`, `main.py`, `config/`, `tests/`, docs
**Test status**: 155 passed (1.46s) · **Lint**: ruff declared in pyproject but
not installable in the active `venv` (see H-2)

This is the deliverable for the request *"review the project and find what must
be structurally improved."* Findings are ranked. Each has evidence (file:line),
why it matters, and a concrete fix. IDs are referenced from `architecture.md`.

---

## Overall Health

The codebase is **well-architected at the layer level** — clean ABCs
(`BaseStrategy`, `BaseBroker`, `BaseDataProvider`), Pydantic domain models, a
strategy registry, dependency injection in `main.py`, look-ahead-safe backtest,
and a genuinely good `docs/DESIGN.md`. Test count is healthy (155) and the core
risk/execution logic is tested.

The structural debt is concentrated where the project **grew a second
orchestration path (the agent) on top of the first** without refactoring the
shared seams. The result is duplication, a dual-mode risk manager toggled by a
boolean, a broker abstraction that leaks, and design docs that no longer match
the code. None of this is broken today — but it is exactly the kind of debt that
makes the next change risky. These are the "must improve" items.

---

## MUST IMPROVE (structural)

### S-1 · Risk-exit logic is implemented three times
**Evidence**:
- `TradingEngine._check_risk_exits` (`src/trading/engine.py:208`)
- `TradingEngine._check_symbol_risk_exit` (`src/trading/engine.py:237`)
- `DecisionExecutor.run_risk_exits` (`src/agent/executor.py:264`)

All three do the same dance: refresh position prices → call
`risk_manager.check_stop_loss` + `check_take_profit` → submit the resulting
orders, differing only in scope (all symbols / one symbol / agent backup).
**Why it matters**: a change to exit semantics (e.g. trailing stops, partial
exits) must be made in three places and kept consistent; they already differ
subtly (the agent version passes `protected_symbols`, the engine versions don't).
**Fix**: extract a single `RiskExitRunner` (or a method on RiskManager that takes
broker + portfolio + optional symbol/protected set) and have all three callers
delegate to it. One implementation, three thin call sites.

### S-2 · `RiskManager` is two classes wearing one, toggled by a boolean
**Evidence**: `use_bracket_orders` flag (`src/risk/manager.py:50`) switches
`_handle_buy` between `_build_bracket_buy` and `_simple_buy`
(`src/risk/manager.py:134-141`); `DecisionExecutor.__init__` **mutates the
injected instance** with `self.risk_manager.use_bracket_orders = True`
(`src/agent/executor.py:55`).
**Why it matters**: (a) a single object has two behavior modes that are never
exercised together, making it hard to reason about; (b) mutating an injected
dependency at construction is a side effect that breaks the "inject a configured
object" contract `main.py` otherwise follows — if anything else shares that
RiskManager, the flip leaks. The flag's docstring still frames bracket mode as a
not-yet-default "Phase 3" opt-in, but it has shipped as the agent default.
**Fix**: make the mode a construction-time choice (pass `use_bracket_orders` in
the constructor — `main.py:309` already does this for the agent path; the
executor mutation at `executor.py:55` is then redundant and should be removed),
or split into a small strategy/policy object. Drop the "Phase 3 / disabled by
default" framing from the docstring.

### S-3 · Layering violation: `src/` reaches into the config singleton
**Evidence** (`grep "from config.config import"` inside `src/` → 7 hits):
`strategy/llm/llm_strategy.py:12`, `strategy/llm/auto_improver.py:47`,
`agent/orchestrator.py:45`, `agent/executor.py:59`, `agent/equity_log.py:112`,
`trading/modes/agent.py:84`, `agent/tools/__main__.py:22`.
**Why it matters**: DESIGN.md states the system uses dependency injection and
that lower layers don't depend on config. `main.py` injects settings explicitly,
but these modules instead pull `get_settings()` themselves — a hidden global
dependency that makes them harder to test (must patch a singleton), couples
library code to the config module, and lets the `universe`/`model`/`experiment`
values enter through two different doors.
**Fix**: pass the needed values in via constructor/params (the orchestrator and
executor already accept `universe`/`model` args — the lazy `get_settings()`
fallback is the leak). Keep `get_settings()` usage confined to `main.py` and the
`agent/tools` CLI entry point.

### S-4 · The broker abstraction leaks (duck-typing around `BaseBroker`)
**Evidence**:
- `getattr(self.executor.broker, "_client", None)` to detect Alpaca and rebuild
  the trade ledger only for it (`src/trading/modes/agent.py:82-89`) — reaches
  into a **private** attribute.
- `portfolio_provider: Callable[[], object]` + `getattr(portfolio, "positions")`
  (`src/agent/orchestrator.py:39, 64`) instead of typing it as
  `Callable[[], PortfolioState]`.
- `is_market_open()` / `get_open_orders()` are on `BaseBroker` but only
  meaningful for Alpaca (default `True` / `[]`), so behavior silently differs by
  concrete type.
**Why it matters**: the whole point of `BaseBroker` is that callers don't know
which broker they have. These bypasses reintroduce that coupling and make
`SimulatedBroker` a partial citizen for the agent path.
**Fix**: add the capability to the ABC explicitly — e.g. a
`reconstruct_closed_trades(...)` (default raising/empty) or a small `TradeLedger`
port — instead of `getattr(_client)`. Type `portfolio_provider` as returning
`PortfolioState`.

### S-5 · Design docs and "Phase N" scaffolding now contradict the code
**Evidence**:
- `docs/DESIGN.md` architecture (section 3) **omits the entire agent
  subsystem** — the primary `--mode agent` path. Its "known issues" §9 still
  lists the already-fixed realtime bug.
- `src/agent/orchestrator.py:8` docstring: *"executing via RiskManager/Broker is
  Phase 3"* — but `DecisionExecutor` does exactly that today. Stale and
  misleading to the next reader.
- 6 `Phase 2/3/R2` scaffolding comments remain in `src/` (`risk/manager.py:34,
  287`, `orchestrator.py:8,51,54`, `session.py:249`).
- `README.md` lists "tests (42개)" (actually 155), the feature table omits
  `--mode agent` and the LLM strategy, and `session.py:248` still has a
  superseded `research_prompt()` helper described as "Phase 2 will enrich".
**Why it matters**: docs that lie are worse than none — they actively mislead
the next change. The "Phase N" language describes a migration that has completed.
**Fix**: update DESIGN.md §3/§9 to include the agent path and current issues;
strip "Phase N" framing from shipped code; refresh README (modes, test count,
LLM/agent features); delete the dead `research_prompt()` if unused.

---

## SHOULD IMPROVE

### Q-1 · Ad-hoc, duplicated file persistence (no state/workspace layer)
State is written by hand in many places with bespoke try/except: executor cursor
`.executor_state.json` (`executor.py:67-79`), session markers `.sessions/*.json`
(`session.py:123-150`), journal `decisions.jsonl` + `positions/*.md`
(`journal.py`), and `turns/equity/trades.jsonl`. Each re-implements
read-json-or-default and `mkdir(parents=True)`. **Fix**: a thin `WorkspaceStore`
that centralizes path resolution + safe JSON/JSONL read/write; the `workspace/`
root is currently recomputed in `journal.py` via `parents[2]` and passed around
loosely.

### Q-2 · Sell sizing truncates and force-mins to 1 share
`RiskManager._handle_sell` does `qty = int(position.qty * sell_pct)` then forces
`qty = 1` if `<= 0` (`src/risk/manager.py:271-273`). With fractional positions
(Alpaca supports them; `Order.qty` and `Position.qty` are `float`), this both
truncates and can oversell a sub-1-share position. **Fix**: keep fractional qty
(or round to the broker's lot rules explicitly), and cap at `position.qty`.

### Q-3 · `get_status()` hardcodes the mode
`src/trading/engine.py:282` returns `"mode": "live"` regardless of actual mode
(already noted in DESIGN.md §9.2 but unfixed). **Fix**: pass the real mode into
the engine or derive it.

### Q-4 · Test coverage gaps on the riskiest modules
Well-tested: risk, executor, execution, strategies, backtest, core, agent
journal/logs. **Untested**: the entire `strategy/llm/` subsystem (6 modules, the
most complex per DESIGN.md), `data/providers/*`, `TradingEngine` cycle,
`trading/modes/*` (agent/batch/realtime), `AgentSession` (the CLI subprocess
wrapper), and `config`. **Fix**: prioritize `TradingEngine.run_cycle`,
`LLMStrategy._parse_llm_response` (the 4-stage fallback), and `AgentSession`
command-building / session-rollover (injectable `runner` already supports this).

### Q-5 · Pervasive lazy/local imports used as a crutch
Imports inside functions appear throughout (`main.py` deliberately defers heavy
deps like torch — fine), but also in `orchestrator._run` (turn_log),
`modes/agent._eod` (equity_log/review/trades_log), executor, etc. Some are
masking the S-3 config coupling and the agent↔trading import direction. **Fix**:
after S-3, hoist the non-heavy ones to module top so dependencies are visible;
keep only the genuinely heavy/optional ones lazy and comment why.

---

## HYGIENE / LOWER PRIORITY

### H-1 · Short positions are half-modeled
`PositionSide.SHORT` exists in `core/types.py` but risk/execution assume long-only
(`_resolve_stop`, sell paths). Either remove the enum value or mark it explicitly
unsupported so it isn't mistaken for a working path. (DESIGN.md §9.5 notes this.)

### H-2 · Dev environment can't lint; two venvs
The active `venv/` lacks the dev deps declared in `pyproject.toml` — `ruff` is
absent (`python -m ruff` fails) and `pytest-asyncio` is missing (pytest warns
`Unknown config option: asyncio_mode`). Both `venv/` and `.venv/` exist (both
gitignored). **Fix**: standardize on one env and `pip install -e ".[dev]"` so the
declared tooling actually runs; then wire `ruff` into the workflow/CI.

### H-3 · Repo hygiene
`__pycache__/` is committed at repo root; empty-ish `models/`, `notebooks/`,
`data/` and a `todos/` dir are tracked. Confirm intent or clean up.

---

## Prioritized Recommendation (suggested order)

1. **S-5** (docs/comments) — cheap, immediately de-risks every later change.
2. **S-3** (inject config) — unblocks testing and clarifies layering.
3. **S-1 + S-2** (unify risk-exit logic; fix RiskManager dual-mode) — the core
   structural consolidation; do together since both touch RiskManager.
4. **S-4** (broker port for ledger/market-clock) — removes the last leak.
5. **Q-1, Q-4** — state layer + tests on the now-clean seams.
6. Hygiene (H-1..H-3) as you touch the areas.

> S-1 through S-4 are the items I'd call **"must" structurally**. They are not
> bugs — the system works and tests pass — but they are load-bearing seams that
> are currently duplicated, mutated, or leaking, and every future feature pays
> interest on them.

---

## Addendum: Closer-Inspection Bugs (B-series)

Found on a second, deeper pass through logic the first sweep didn't fully read
(position sizing, backtest engine/metrics, SimulatedBroker, portfolio-value
sources). These are genuine correctness bugs, not just structure.

### B-1 · Backtest metrics counted every fill as a trade — **FIXED (commit 9384b3c)**
`BacktestEngine` recorded each buy and sell as a row in `trades`, and BUY rows
got `pnl=0.0`. So `total_trades = len(trades)` was ~2× the real round-trip count
and `win_rate = wins/len(trades)` was ~halved (a 100%-winning strategy showed
~50%). **Fix**: reuse `match_round_trips` (moved to `src/core/trades.py`, shared
with the live ledger) — metrics are computed from closed round-trips.

### B-2 · Backtest evaluated stops/take-profits on the close only — **FIXED (commit 9384b3c)**
`set_current_price` was fed only the close and the polled check compared against
it, so a bar whose **low** pierced the stop but **closed** above it never stopped
out — optimistic vs live, where the resting bracket triggers intra-bar. The
SimulatedBroker's intra-bar resting-leg machinery existed but the backtest didn't
use it. **Fix**: feed bar high/low and arm resting OCO protection on entry so
exits trigger intra-bar at the trigger price (mirrors live); also removed the
backtest's inline polled-exit block (the S-1 "4th site").

### B-3 · Sell sizing truncated to int and forced a 1-share minimum — **FIXED (commit 816f298)**
`RiskManager._handle_sell` did `int(position.qty * sell_pct)` then `if qty<=0: qty=1`.
A full exit of a 0.5-share position computed `int(0.5)=0` → forced 1 → tried to
oversell; inconsistent with the float-qty stop/take exits. **Fix**: fractional-safe
sizing — full exit sells exact `position.qty`, `sell_pct→0` returns no order.

### M-1 · `PortfolioState.total_value` is a dead duplicate of `equity` — **FIXED (commit pending)**
Nothing read `total_value`; every caller uses the `equity` field (set by the
broker). The property recomputed `cash + Σ market_value`, which can diverge from
`equity` if position prices are stale — a latent trap for a future caller.
**Fix**: removed the property; `equity` is now the single source of truth, with a
comment on the model warning against re-adding a divergent duplicate. The only
reference (a `test_core.py` assertion) was retargeted to `equity`.
