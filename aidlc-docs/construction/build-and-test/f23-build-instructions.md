# F23 Build Instructions

## Prerequisites
- Python 3.11+ venv with project dependencies
- `claude` CLI (for agent session — build-only 단계에서는 불필요)

## Dependency Check
```bash
cd .claude/worktrees/F23
python -m pip install -e ".[dev]" 2>&1 | tail -5
```

## Build — Import Smoke Test
```bash
cd .claude/worktrees/F23
python -c "
from config.config import Settings, MultiAgentConfig, AgentConfig
from src.agent.tools import market
from src.agent.journal import Journal, LessonRecord
from src.agent.orchestrator import AgentTradingLoop, SubAgentTask, SubAgentReport
from src.agent.session import AgentSession
from src.agent import prompts
print('All imports OK')
"
```

Expected output: `All imports OK`

## Config Round-trip
```bash
python -c "
from config.config import Settings
s = Settings(**{
    'multi_agent': {'enabled': True, 'n_agents': 3, 'mode': 'sequential'},
    'agent': {'research_start_before_open': 90, 'research_end_before_open': 10},
})
assert s.multi_agent.enabled == True
assert s.multi_agent.n_agents == 3
assert s.agent.research_start_before_open == 90
print('Config round-trip OK')
"
```

Expected output: `Config round-trip OK`
