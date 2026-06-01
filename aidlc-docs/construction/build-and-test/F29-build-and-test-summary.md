# F29 Build & Test Summary — `codebase-orientation`

> **Track**: F29 · **Date**: 2026-06-02
> **Unit**: `codebase-orientation` (single unit)

## Build

### Python (daemon)
```bash
# No new dependencies; verify imports are clean
python -c "from src.agent.steering.runtime import SteeringRuntime; from src.agent.steering.channel import SteeringChannel; print('OK')"
```

### TypeScript (MCP / launcher)
```bash
# Submodule must be initialized for typecheck
cd operator-console/cli && bun run typecheck
# Manual verification: the changed files (parser.ts, steer-handler.ts, filedrop.ts, mcp-server.ts)
# follow existing patterns exactly — no new imports, no API changes.
```

## Unit Tests

### Python
```bash
python -m pytest tests/test_codebase_tree.py -v
# 11 tests: tree prefix/content/exclusion/descriptions/key-files + channel atomic write
# + synthetic tree root override + egg-info glob
```

### TypeScript
```bash
# Submodule required for TS test runner
cd operator-console/cli && bun test operator-console/test/
# Manual smoke: steer_read{command:/codebase} → returns tree text from codebase.json
```

## Integration / Regression

### Full Python regression
```bash
python -m pytest tests/ -x -q
# Expected: 574 passed (563 baseline + 11 new), 0 failures
```

### Docker-verify attach smoke (optional, manual)
```bash
./scripts/worktree-setup.sh F29 --docker-verify
docker compose -f docker-compose.verify.yml run --rm verify attach
# In supervisor console: steer_read{command:/codebase}
# Should return the project directory tree with package descriptions
```

## Results (2026-06-02)

| Test | Result |
|------|--------|
| Python unit tests (test_codebase_tree.py) | **11 passed** |
| Full Python regression (574 tests) | **574 passed, 0 failures** |
| Python import smoke | **OK** |
| `pip check` | **clean** (0 new deps) |
| TS typecheck | **deferred** (submodule not initialized in worktree) |
| docker-verify attach smoke | **deferred** (manual, requires docker) |

## Verification Items
- [x] `steer_read{command:/codebase}` verb registered in parser READ_VERBS
- [x] `SteeringChannel.publish_codebase()` writes atomic codebase.json
- [x] `SteeringRuntime._publish_codebase_tree()` scans repo at startup (depth=2)
- [x] Tree excludes build artifacts, caches, hidden dirs, egg-info
- [x] Tree includes package descriptions and key file pointers
- [x] `{AUTOSTOCK_ROOT}` prefix for path resolution
- [x] `steer_read` MCP tool description includes `/codebase` usage hint
- [ ] docker-verify supervisor attach → `/codebase` returns tree (user manual check)
