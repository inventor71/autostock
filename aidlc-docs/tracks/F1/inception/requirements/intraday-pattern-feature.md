# Feature: Dynamic Intraday Pattern Detection — Feasibility & P0 Requirements

**Stage**: INCEPTION → Requirements Analysis (intent + feasibility), minimal depth.
**Date**: 2026-05-28
**Status**: P0 (exploratory) scoped and awaiting code-gen approval.

## 1. Original request (intent)

Track each day's intraday (open→close) shape; recurring patterns sometimes appear
(e.g. an opening sell-off that recovers; an early surge that — combined with community
reaction — precedes a fade). Patterns are **non-stationary**: they persist for weeks to
months but never repeat exactly and eventually shift. Goal: an LLM that *records* such
patterns and *dynamically detects/uses* them. Likely needs daily intraday graphs + real-time
community-reaction scraping. User wants to validate the **idea's viability before building**.

## 2. Feasibility verdict (honest)

**Valid as an observation; risky in the naive "LLM predicts shifting patterns" form.**

- **Real:** the phenomena exist (gap fill / overreaction reversal; sentiment-extreme
  blow-off). The non-stationarity observation is exactly correct — it is what causes alpha
  decay / regime change, the hardest part of the problem.
- **The killer constraint:** with patterns shifting every few weeks, each regime gives only
  ~20–60 sessions of data — too little to validate before it changes. The agent+web path is
  already **not backtestable** (decision #7 in the LLM-trader design: lookahead /
  non-determinism), and historical *real-time community reaction* data is not cheaply
  obtainable, making historical validation worse. Edge can only be confirmed forward (paper),
  during which the regime shifts again.
- **Dominant failure mode:** an LLM reading a journal will confidently narrate patterns that
  are noise (hindsight/story bias) — it will *feel* like learning while overfitting to recent
  randomness.
- **Weak spots:** LLMs read raw number series poorly (prefer deterministic features over
  "graphs"); community scraping is fragile (ToS, bots, pump-and-dump, low S/N) and should be
  an API-sourced *secondary contrarian* feature, never the thesis.

**Reframe that makes it valid:** not "predict patterns" but "structured hypothesis lifecycle
with honest out-of-sample scoring" — compute deterministic intraday features, let the LLM
state *falsifiable* hypotheses with a validity window, score them forward (existing EOD
review loop), and only let a hypothesis influence sizing after it survives N independent
forward observations. This fits the existing agent / journal / `lessons.md` / call-vs-outcome
architecture and the repo's "deterministic where possible, backtest-live parity" discipline.

## 3. Phasing

| Phase | Scope | Backtestable? | Trading impact |
|-------|-------|---------------|----------------|
| **P0** | Deterministic intraday-feature store + pattern-existence analysis | **Yes** | None |
| P1 | Falsifiable hypothesis schema in journal + EOD out-of-sample scoring/graduation | Partial | None |
| P2 | Community sentiment as an API-sourced secondary contrarian feature | No | None |
| P3 | Graduated hypotheses inform sizing; paper-only behind a success-criteria gate | No | Paper |

**User decision (2026-05-28): build P0 only first (exploratory).** P0 answers the empirical
question — *do these patterns statistically exist and persist?* — with real data, then we
re-decide P1+.

## 4. P0 Requirements

**Goal:** a deterministic, persistent intraday-feature dataset for the universe, plus a small
analysis that reports whether named candidate patterns have a conditional edge **and how that
edge drifts over time** (the non-stationarity, made visible). No LLM, no web, no trading.

### Functional
- **FR-1 Feature computation (pure):** given one symbol's intraday minute bars for one session
  + prior close, compute a feature record. Candidate features: `gap_pct`, first-30-min return
  & range, VWAP deviation at close, time-of-intraday-high/low (minutes from open), max
  drawup/drawdown from open, `close_loc` (where in range close lands), open→close return,
  last-30-min return, relative volume, realized intraday vol. Pure, no I/O.
- **FR-2 Persistent store:** idempotent upsert keyed by `(date, symbol)`; read by
  symbols/date-range. Backend: per-symbol **CSV** under `data/intraday/` (gitignored; no new
  dependency — pyarrow absent, pandas 3.0 present). Hidden behind a store abstraction so we can
  swap to Parquet later without touching callers.
- **FR-3 Collection job:** for each universe symbol (`config/settings.yaml` `trading.symbols`),
  fetch the day's minute bars via the existing `BaseDataProvider.get_bars(timeframe=MINUTE_5)`,
  compute features (FR-1), upsert (FR-2). One callable + a CLI to (a) backfill the last N
  available days and (b) run "today". Reuses existing providers/universe.
- **FR-4 Pattern-existence analysis (the deliverable):** for a small set of named hypotheses
  (condition → outcome, e.g. "gap-down >X% → positive open→close"), report N, baseline vs
  conditional mean outcome, hit rate, a simple significance proxy (t-stat / CI), and a
  **rolling-window stability** view showing how the conditional edge changes across time.
  Output a markdown/JSON report.

### Non-functional
- Deterministic and unit-testable (network-free tests via injected providers / synthetic bars),
  matching the repo's PBT-partial discipline for the pure feature/analysis functions.
- No new runtime dependency (CSV, stdlib + pandas/numpy already present).
- Provider history limit acknowledged: yfinance intraday ≈ last 60 days; Alpaca serves minute
  bars back to 2016 (free IEX feed = volume subset). P0+ added an Alpaca date-range backfill
  (`--provider alpaca --start --end`) for deep multi-year history; otherwise accumulate forward.

### Out of scope (P0)
LLM, journal hypotheses, community sentiment, position sizing, any live/paper trading effect.

### Success criteria (P0)
1. Backfill + persist intraday features for the universe.
2. Produce a stability report for ≥2 candidate patterns.
3. The report is the artifact we use to decide whether P1+ is worth building.

## 5. Proposed implementation plan (for code-gen approval)

- [ ] `src/data/intraday_features.py` — pure feature functions (FR-1) + tests.
- [ ] `src/data/intraday_store.py` — CSV-backed `IntradayFeatureStore` (FR-2) + round-trip tests.
- [ ] `src/data/intraday_collector.py` — universe collection/backfill over a data provider (FR-3).
- [ ] `src/data/intraday_analysis.py` — hypothesis conditional-edge + rolling stability (FR-4)
      + tests on synthetic data with a known injected pattern.
- [ ] CLI entry: `python -m src.data.intraday_collector` (backfill/today) and an analysis command.
- [ ] Extension compliance: SECURITY-03/11/15 (no secrets; isolated; fail-closed on bad bars);
      PBT-partial on pure feature/analysis functions.
