# F91 — Build & Test Summary

## Change
Single-line fix in `src/signals/sentiment_sweep.py`:

```python
# before
append_sweep(records, root=self._root)
# after — thread the sweep's own clock so persistence partitions by the same
# logical clock _in_window was evaluated against (no second wallclock read).
append_sweep(records, root=self._root, ts=now_et)
```

`append_sweep` already accepted optional `ts: datetime | None` — no signature change.

## Root cause
`append_sweep(... ts=None)` → `now = ts or datetime.now().astimezone()` → ET-date partition
chosen by a **second, independent wallclock read**, separate from the sweep's `self._now()`.
- Tests injected `now_fn=lambda: ET_NOON` (2026-06-12) and read with `load_recent(now=ET_NOON)`,
  but records were written to today's real-date file → reader's window missed them.
- Production hazard: the two reads can straddle ET midnight → record lands in the wrong ET-date
  file (rollover torn-partition, [[timeline-midnight-crossing-regions]]-class).

## Test results
| Suite | Before | After |
|-------|--------|-------|
| `tests/signals/test_sentiment_sweep.py` | 3 failed / 10 passed | **13 passed** |
| `tests/signals/` (full) | (3 fail) | **165 passed** |

Run with the main venv (`venv/bin/python -m pytest`), 2026-06-22.

## Scope / risk
- No API/signature change; behavior identical in the common case (real clock), correct under
  injected clock + at ET-midnight rollover.
- No network/secret/IO surface change → Security Baseline N/A.
- Standalone, merges independently of F88 (F88 does not touch sentiment files).

## Post-merge guide
Skipped — purely internal correctness fix, no new behavior/config/env a person observes in
production (the daemon's persisted ET-date file simply matches the sweep clock).
