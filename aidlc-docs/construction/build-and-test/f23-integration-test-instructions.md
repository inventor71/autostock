# F23 Integration Test Instructions

## I1: Multi-Agent Toggle Integration
Verify that `multi_agent.enabled` correctly routes between single-session and multi-agent paths.

```bash
cd .claude/worktrees/F23
python -m pytest tests/test_multi_agent.py::TestDisabledFallback \
  tests/test_multi_agent.py::TestSequentialResearch \
  tests/test_multi_agent.py::TestParallelResearch -v
```

Pass condition: disabled→1 call, Mode B N=3→3 calls, Mode C→sub-agents + synthesis.

## I2: Full Regression
Verify no breakage in existing functionality.

```bash
cd .claude/worktrees/F23
python -m pytest tests/ -x --tb=short -q
```

Pass condition: 482 passed, 0 failures.

## I3: Config → Orchestrator Wiring
Verify settings.yaml config reaches the orchestrator.

```bash
cd .claude/worktrees/F23
python -c "
from config.config import get_settings
s = get_settings()
assert hasattr(s, 'multi_agent')
assert isinstance(s.research, dict)
print(f'multi_agent.enabled={s.multi_agent.enabled}')
print(f'multi_agent.n_agents={s.multi_agent.n_agents}')
print(f'agent.research_start_before_open={s.agent.research_start_before_open}')
print('Config wiring OK')
"
```

Pass condition: prints valid values from settings.yaml, no errors.

## I4: New CLI Tools Smoke
```bash
cd .claude/worktrees/F23
# Test each new tool command parses correctly
python -m src.agent.tools earnings AAPL 2>&1 | python -m json.tool > /dev/null && echo "earnings OK"
python -m src.agent.tools insider AAPL 2>&1 | python -m json.tool > /dev/null && echo "insider OK"
python -m src.agent.tools analyst_upgrades AAPL 2>&1 | python -m json.tool > /dev/null && echo "analyst_upgrades OK"
python -m src.agent.tools institutional AAPL 2>&1 | python -m json.tool > /dev/null && echo "institutional OK"
python -m src.agent.tools macro 2>&1 | python -m json.tool > /dev/null && echo "macro OK"
python -m src.agent.tools lesson add --takeaway "test lesson" 2>&1 | python -m json.tool > /dev/null && echo "lesson add OK"
```

Pass condition: all 6 commands print `OK` (note: `earnings`/`insider` etc. do live yfinance calls and may fail on network issues — this is a CLI plumbing test, not data validation).

## I5: Existing Commands Still Work
```bash
cd .claude/worktrees/F23
python -m src.agent.tools fundamentals AAPL 2>&1 | python -m json.tool > /dev/null && echo "fundamentals OK"
python -m src.agent.tools quote AAPL 2>&1 | python -m json.tool > /dev/null && echo "quote OK"
python -m src.agent.tools indicators AAPL 2>&1 | python -m json.tool > /dev/null && echo "indicators OK"
```

Pass condition: existing commands unaffected.
