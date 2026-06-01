# F23 Performance Test Instructions

## PF-1: Sub-Agent Workspace Isolation Overhead
Mode C creates temp directories + copies files for each sub-agent.

```bash
cd .claude/worktrees/F23
python -c "
import tempfile, time, shutil
from pathlib import Path
from src.agent.journal import Journal

j = Journal()
j.init()
(Path(j.root) / 'regime.md').write_text('bull market regime\n' * 100)
(Path(j.root) / 'positions').mkdir(exist_ok=True)
(Path(j.root) / 'positions' / 'AAPL.md').write_text('long AAPL\n' * 100)

start = time.perf_counter()
for _ in range(3):
    tmp = Path(tempfile.mkdtemp())
    for name in ('CLAUDE.md', 'lessons.md', 'regime.md', 'watchlist.md'):
        src = j.root / name
        if src.exists():
            shutil.copy2(src, tmp / name)
    shutil.copytree(j.root / 'positions', tmp / 'positions')
    shutil.rmtree(tmp)
elapsed = time.perf_counter() - start
print(f'3 workspace creations: {elapsed:.3f}s ({elapsed/3*1000:.0f}ms avg)')
"
```

Acceptance: < 100ms per workspace creation (disk I/O only, no network).

## PF-2: Config Load Time Impact
Multi-agent config adds small overhead to Settings init.

```bash
cd .claude/worktrees/F23
python -c "
import time
from config.config import get_settings
get_settings.cache_clear()
start = time.perf_counter()
s = get_settings()
elapsed = time.perf_counter() - start
print(f'Settings load: {elapsed*1000:.1f}ms')
"
```

Acceptance: < 50ms (parsing YAML + Pydantic validation).

## PF-3: Research Turn Token Estimate (NFR)
Benchmark unavailable — requires live claude CLI session. Estimates only:
- Mode B (N=3): ~1.5× single-session tokens (longer context, 3 turns in same session)
- Mode C (N=3): ~3× single-session tokens (2 sub-agents + Manager synthesis)
- Single session baseline: ~100K-200K input tokens (varies by universe size)

## PF-4: Test Suite Performance
```bash
cd .claude/worktrees/F23
python -m pytest tests/test_signal_tools.py tests/test_multi_agent.py --durations=5 -q
```

Acceptance: all 51 F23 tests complete in < 3s.

## Performance Notes
- No new runtime dependencies — no dependency resolution overhead
- No network calls in unit tests (all mock-based) — deterministic timing
- Mode C workspace creation uses local filesystem only (no network)
- Multi-agent research is pre-market — wall-clock latency is bounded by `research_start_before_open - research_end_before_open` (default 55 min)
