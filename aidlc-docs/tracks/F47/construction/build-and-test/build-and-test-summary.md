# F47 surge-detection — Build & Test Summary

> 2026-06-03 | Worktree: `.claude/worktrees/F47` | Branch: `feat/F47`

## Test Results

| Category | Count | Result |
|----------|-------|--------|
| New surge unit tests | 31 | ✅ All pass |
| Full regression | 680 | ✅ All pass (0 regressions) |
| Import smoke | — | ✅ Clean |

## Test Modules

| File | Tests | Description |
|------|-------|-------------|
| `tests/test_surge_store.py` | 14 | SurgeStore JSONL read/write, idempotency, analyses, torn-line safety |
| `tests/test_surge_detector.py` | 10 | SurgeDetector scan, threshold, fail-isolation, sorting |
| `tests/test_surge_tools.py` | 7 | Agent tools: surge-list, surge-analyze (ok/error/validation) |

## Build Verification

- **0 new runtime dependencies** — stdlib + pydantic + loguru (all pre-existing)
- `pip check` — clean (no conflicts)
- Import smoke: `from src.surge import SurgeRecord, SurgeDetector, SurgeStore` — OK

## File Manifest

| File | Action | LOC |
|------|--------|-----|
| `src/surge/__init__.py` | New | 9 |
| `src/surge/records.py` | New | 67 |
| `src/surge/settings.py` | New | 25 |
| `src/surge/store.py` | New | 148 |
| `src/surge/detector.py` | New | 120 |
| `src/data/base.py` | Modify | +23 |
| `src/agent/tools/market.py` | Modify | +67 |
| `src/agent/tools/__main__.py` | Modify | +11 |
| `src/agent/prompts.py` | Modify | +24 |
| `src/agent/orchestrator.py` | Modify | +3 |
| `src/trading/modes/agent.py` | Modify | +24 |
| `config/settings.yaml` | Modify | +4 |
| `tests/test_surge_store.py` | New | 155 |
| `tests/test_surge_detector.py` | New | 115 |
| `tests/test_surge_tools.py` | New | 80 |
| **Total** | | **~875 LOC** |

## Key Design Decision (Mid-Construction Pivot)

저장 위치를 `steering/watch_surge/`에서 `workspace/surge/`로 변경함.
- Agent LLM이 생산하고 소비하는 데이터 → workspace/가 올바른 위치
- `decisions.jsonl`, `lessons.jsonl`과 동일한 패턴
- deny-hook으로 steering/에 접근 불가능한 agent가 자신의 분석을 읽을 수 있어야 함

## Merge Readiness

- [x] All 680 tests green
- [x] 31 new surge tests green
- [x] 0 new runtime deps
- [x] No regression
- [x] Worktree clean (uncommitted changes on feat/F47)
