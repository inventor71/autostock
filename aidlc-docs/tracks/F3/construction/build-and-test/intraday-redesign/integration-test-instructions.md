# Integration Test Execution — Unit `intraday-redesign` (F3)

> F3 is a single unit, but it integrates with the **main `src/agent/steering/` engine** (F4) and the agent turn/executor path. These tests exercise the seams across the concurrency engine, the snapshot/bus, and the daemon wiring.

## Automated integration tests (run offline)
```bash
cd /home/jihoonpark/Project/autostock/.claude/worktrees/intraday-redesign
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest \
  tests/test_intraday_integration.py tests/test_intraday_wiring.py tests/test_intraday_snapshot.py -q
```

### Seams covered
1. **Wake path through the real engine** (`test_intraday_integration.py`): `WakeDetector → ReconcileWorker.trigger(kind="wake") → TurnCoordinator.reconcile_turn` with the actual primitives (not fakes). Asserts the typed-event buffer is drained at FIRE time (coalesced into one turn).
2. **Skip-if-busy (V3, C-1/C-2)**: while a wake turn holds the single `turn_lock`, a `try_scheduled_turn` arriving in the same slot returns `("skipped", …)` — **skips, does not queue**.
3. **Daemon wiring** (`test_intraday_wiring.py`): `AgentTradingMode._intraday` assembles a brief and passes it to `run_intraday` when steering is on; with `steering=None` it falls back to the legacy prompt and builds no F3 components (NFR-8).
4. **Snapshot↔fills↔brief** (`test_intraday_snapshot.py`): `publish_snapshot` (on the bus worker) collects new fills into `last_snapshot`; the BriefAssembler reads that in-proc cache (never the broker).

## Manual / live integration (requires the daemon + paper account)
These are NOT in CI (need a live `claude` session + open market for full effect). Run on the operator machine:

1. **End-to-end wake on a real fill** — start `python main.py --mode agent --steering`; place (or let the agent place) a paper order; within ~5s the snapshot publisher picks up the activity, the wake detector fires a `wake` turn, and the agent's journal reflects the fill (no inference). Verify in `workspace/turns.jsonl` a `wake` turn appears out-of-band (not on a 15-min boundary).
2. **Watch trigger → ADJUST_STOP judgement** — agent runs `watch set RTX close_above 182`; when the last 5-min bar closes above 182, a `watch_trigger` wake fires and the agent judges whether to ADJUST_STOP (advisor-only; Python only detects).
3. **entries_halted suppression** — operator `/halt_entries`; confirm abnormal-up / entry-intent watches do NOT wake, while new_fill / protective / sell-side watches still do (Q7=A).
4. **paused** — operator `/pause`; confirm no wake turns fire (only a suppression log), and protection (risk-exits) still runs.

## Cross-process / channel integration
- `watch.jsonl` is written by the **agent subprocess** (`watch` tool) and read by the **daemon** (WatchStore) — covered by torn-safe `read_complete_lines` + the watch unit tests. A live cross-process check: run the `watch set` tool, then confirm the daemon's `WatchStore.active()` sees it.

## Expected results
- Automated: all green (part of the 347 full-suite pass).
- Manual: a `wake` turn observed within the detector cadence after a fill; gating behaves per RunState.
