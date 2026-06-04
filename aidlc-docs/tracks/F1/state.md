# Track F1 — Dynamic Intraday Pattern Detection (archived pre-partition history)

> Migrated 2026-06-04 from the root `aidlc-state.md` archived section into this track's
> `state.md` (concurrent-tracks partition rule: root file = Track Registry only). This is
> historical record for a completed/abandoned track — the registry row in
> `aidlc-docs/aidlc-state.md` is authoritative for final status. Design/plan artifacts live
> alongside under `aidlc-docs/tracks/F1/`.

## New Feature Track: Dynamic Intraday Pattern Detection (F1)
- **Started**: 2026-05-28. **Stage**: INCEPTION → Requirements Analysis (intent/feasibility), minimal.
- **Requirements doc**: `aidlc-docs/inception/requirements/intraday-pattern-feature.md`
- **Feasibility verdict**: observation valid; naive "LLM predicts shifting patterns" risky
  (non-stationarity → ~20–60 sessions/regime, not backtestable, narrative-overfitting risk).
  Reframed to "falsifiable hypothesis lifecycle + honest out-of-sample scoring" on the existing
  agent/journal/EOD-review architecture. Phased P0→P3.
- **User decision**: build **P0 only first (exploratory)** — answer "do these patterns
  statistically exist & persist?" with real data, then re-decide P1+.
- **P0 plan — DONE 2026-05-28** (15 new tests; suite 179 → 194 green):
  - [x] `src/data/intraday_features.py` — pure per-session features + `FEATURE_COLUMNS`
  - [x] `src/data/intraday_store.py` — CSV-backed `IntradayFeatureStore` (`data/intraday/`), idempotent on (date,symbol)
  - [x] `src/data/intraday_collector.py` — `sessionize`/`features_for_symbol`/`collect` + CLI (`backfill`/`today`)
  - [x] `src/data/intraday_analysis.py` — `Hypothesis` registry, conditional edge (n/hit_rate/excess/t-stat),
        rolling-window stability, md/JSON report + CLI
  - [x] `tests/test_intraday.py` — features (example + Hypothesis invariants), store round-trip/idempotency,
        collector sessionize/prev-close-chaining/failure-tolerance, analysis injected-pattern vs flat
  - **Live-validated**: real yfinance backfill (AAPL, 14 sessions) → report rendered; rolling view already
    shows a candidate pattern flipping sign across windows (non-stationarity made visible — the intended signal).
  - Decisions: CSV (no new dep; pyarrow absent, pandas 3.0 present, swappable backend), MINUTE_5 bars via
    existing provider, universe from `config/settings.yaml`; no LLM/web/trading in P0.
  - **P0+ (2026-05-28): Alpaca + date-range backfill added** for deep multi-year history. `collect()` takes
    `start`/`end` (limit dropped in range mode); CLI `backfill --provider {yfinance,alpaca} --start --end`.
    2 new collector tests (range vs limit call routing); suite 194 → 196 green. Live-validated: Alpaca pulled
    107,633 AAPL 5m bars (2024-01→2026-05) → 633 sessions; report over 647 sessions shows only
    `gap_down_reversion` flickering (t≈2.8 but n=12 with one window flipping negative) — the small-sample /
    non-stationarity reality, and the case for a full-universe backfill (×~105 → ~100× the conditional n).
  - **Next (user re-decides):** run a full-universe Alpaca backfill, read the stability report, then decide whether
    P1 (hypothesis lifecycle in journal + EOD out-of-sample scoring) is worth building.
