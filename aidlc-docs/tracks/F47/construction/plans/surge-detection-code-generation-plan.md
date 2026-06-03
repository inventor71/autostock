# surge-detection — Code Generation Plan

> 2026-06-03 | Worktree: `.claude/worktrees/F47` | Branch: `feat/F47` | Base: `469fa51`

## Plan Steps

### Step 0: Worktree Setup
- [x] `git worktree add .claude/worktrees/F47 -b feat/F47` → base `469fa51`
- [ ] `cd .claude/worktrees/F47`

### Step 1: `src/surge/` — data models + settings
- [ ] `src/surge/__init__.py`
- [ ] `src/surge/records.py` — SurgeRecord, SurgeAnalysis, SurgeCause
- [ ] `src/surge/settings.py` — SurgeDetectionConfig

### Step 2: `src/surge/store.py` — JSONL store
- [ ] `src/surge/store.py` — SurgeStore (write_records, read_records, append_analysis)
- [ ] Tests: `tests/test_surge_store.py`

### Step 3: `src/surge/detector.py` — surge scanner
- [ ] `src/surge/detector.py` — SurgeDetector.scan()
- [ ] `src/data/base.py` — add `get_daily_bar()` to DataProvider
- [ ] Provider implementations (yfinance, alpaca)
- [ ] Tests: `tests/test_surge_detector.py`

### Step 4: Agent tools
- [ ] `src/agent/tools/market.py` — add `surge_list()`, `surge_analyze()`
- [ ] `src/agent/tools/__main__.py` — add subcommands
- [ ] Tests: `tests/test_surge_tools.py`

### Step 5: EOD integration + config
- [ ] `src/modes/agent.py` — add `_run_surge_scan()` + market-close job
- [ ] `src/agent/prompts.py` — extend `eod_review_prompt()` with surge section
- [ ] `config/settings.yaml` — add `surge:` block

### Step 6: Integration tests + regression
- [ ] Integration test: detector → store → read round-trip
- [ ] Integration test: surge-analyze tool validation
- [ ] Full regression suite
- [ ] PBT tests (Hypothesis) for pure functions

### Step 7: Build & Test
- [ ] All tests green
- [ ] Import smoke test
- [ ] Build verification (pip check)

---

## File Manifest

| File | Action | Lines (est.) |
|------|--------|-------------|
| `src/surge/__init__.py` | New | 5 |
| `src/surge/records.py` | New | 50 |
| `src/surge/settings.py` | New | 20 |
| `src/surge/store.py` | New | 80 |
| `src/surge/detector.py` | New | 70 |
| `src/data/base.py` | Modify | +10 |
| `src/data/providers/yfinance_provider.py` | Modify | +15 |
| `src/data/providers/alpaca_provider.py` | Modify | +15 |
| `src/agent/tools/market.py` | Modify | +40 |
| `src/agent/tools/__main__.py` | Modify | +30 |
| `src/modes/agent.py` | Modify | +20 |
| `src/agent/prompts.py` | Modify | +15 |
| `config/settings.yaml` | Modify | +3 |
| `tests/test_surge_store.py` | New | 60 |
| `tests/test_surge_detector.py` | New | 60 |
| `tests/test_surge_tools.py` | New | 50 |
| `tests/test_surge_integration.py` | New | 40 |
| **Total** | | **~583 LOC** |

## Estimated Timeline
- **Total Steps**: 7
- **Estimated Effort**: ~1 session (small module, 0 new deps)
