# F61 Unit & Property Test Instructions

> Tier 1 — deterministic, network-free, **zero LLM tokens**. Run from the worktree
> with the main venv python.

```bash
# whole signal suite
python -m pytest tests/signals -q

# by area
python -m pytest tests/signals/test_movers.py tests/signals/test_peer_map.py \
  tests/signals/test_readthrough.py tests/signals/test_earnings_cal.py \
  tests/signals/test_brief.py -q                       # example-based units

python -m pytest tests/signals/test_properties.py \
  tests/signals/test_records_roundtrip.py -q           # PBT (Hypothesis)

python -m pytest tests/signals/test_scenarios.py -q    # multi-type corpus S1..S5

python -m pytest tests/signals/test_collector.py \
  tests/signals/test_tools_signals.py -q               # boundary + tools
```

## PBT (Partial mode) coverage
- **PBT-02** round-trip: `test_records_roundtrip` — `model_validate(model_dump()) == x`.
- **PBT-03** invariants: `test_properties` — movers cleared threshold + ⊆ input; read-through
  peers ⊆ universe and exclude trigger; `peers_of(sym)` excludes self.
- **PBT-07** generators: domain strategies (symbols, mover rows, alerts) — no raw-primitive-only.
- **PBT-08** reproducibility: Hypothesis default (shrinking on; seed logged on failure).
- **PBT-09** framework: Hypothesis (existing dev dependency).

## Token protection (NFR-7)
Default run excludes manual/LLM tests via `addopts = -m "not manual"` (pyproject). Nothing in
`tests/` calls the LLM. The agent-judgement harness is `src/signals/eval_readthrough.py` (run
manually — see summary).

Expected: **51 passed** (signals), **838 passed** (full suite).
