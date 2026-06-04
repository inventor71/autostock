# F54 — Unit Test Instructions

```bash
VENV=/home/jihoonpark/Project/autostock/venv/bin/python
cd .claude/worktrees/F54

# short-specific (Unit A risk core + Unit B agent intelligence)
$VENV -m pytest tests/test_short_risk.py tests/test_short_agent.py -q   # 56 passed

# full regression (no behavior change to existing long-only paths)
$VENV -m pytest tests/ -q                                               # 742 passed
```

Key cases:
- Unit A: mandatory short stop, inverted bracket/ratchet/polled, dual breaker,
  squeeze guard, auto-flip, SimulatedBroker short open/cover/bracket, PBT invariants.
- Unit B: short_data squeeze flag, account direction-aware pct, prompt/steering wiring.
