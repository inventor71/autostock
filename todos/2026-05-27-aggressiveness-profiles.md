# Selectable agent "aggressiveness" profiles — plan (deferred)

**Created:** 2026-05-27
**Status:** deferred until the live agent has a baseline + is stable (see prereqs)

## Goal
Let us experiment with how aggressive the PM agent trades by selecting a
**profile** (not a single prompt). A profile bundles a *prompt style* with a set
of *risk-config knobs*, chosen via `settings.yaml`.

## Why deferred (do these first)
- No baseline track record yet (paper account is days old). Can't tell if a
  profile is "better".
- Still surfacing live bugs (session collision, OCO shape, tzdata, cancel race,
  TSLA-unprotected — all found in the first hours live). Stabilize the base loop
  first so a profile's effect is separable from bugs.
- EOD self-review / `lessons.md` loop is not yet proven live — that's the
  intended scorecard.
- Comparison methodology needs to exist (below) before variants are meaningful.

**Prereqs:** a few days of paper track record · EOD/lessons validated ·
position-protection invariant guard in place · fill/error alerting · the daily
equity log (#3, implemented 2026-05-27) accumulating data.

## Design
- `settings.yaml`: `agent.profile: conservative | balanced | aggressive | momentum | contrarian`
- A **profile = risk-config overrides + a prompt preamble** appended to the
  agent's turns (via `--append-system-prompt` or a profile section the turn
  prompts include).
- Knobs a profile sets:
  - `max_position_pct`, `max_portfolio_risk`, `max_stop_distance_pct`, `atr_stop_multiple` (already in RiskConfig — the "aggressive" preset is half this lever already)
  - `conviction_threshold` — min confidence to act (e.g. 0.4 vs 0.7)
  - `max_new_positions_per_day`
  - `entry_style` — chase/market vs wait-for-pullback limit
  - `cash_floor` — keep N% cash vs fully invested
- Prompt preamble per profile, e.g.:
  - conservative: "fewer, higher-conviction names; wait for pullbacks; keep a cash buffer; quick to cut losers."
  - aggressive: "act on momentum and breaking catalysts; more concurrent names; let winners run."

## 5 profiles (sketch)
1. **conservative** — low size, high conviction bar, wide cash floor, tight risk.
2. **balanced** — current defaults.
3. **aggressive** — current "aggressive" risk preset + lower conviction bar, more names.
4. **momentum** — chases strength/breakouts, market entries, trails winners.
5. **contrarian/value** — buys pullbacks/oversold, patient limit entries.

## Evaluation methodology (the hard part)
- Agentic path is **not backtestable** (web search = lookahead/non-determinism).
- One paper account → **sequential A/B** over fixed windows (caveat: different
  market regimes between windows). Log `workspace/equity.jsonl` per window +
  the journal/lessons as the scorecard.
- Better: **multiple Alpaca paper accounts** (separate keys) to run profiles
  **in parallel** over the same window. Cleanest comparison.

## Implementation steps (when picked up)
1. `AgentProfileConfig` in config (name + knob overrides + preamble text).
2. Map selected profile → RiskManager params + a preamble injected into turns.
3. Wire `agent.profile` selection in `run_agent`.
4. Record the active profile in `equity.jsonl` / daily note so results are attributable.
5. Document profiles + how to run an A/B.
