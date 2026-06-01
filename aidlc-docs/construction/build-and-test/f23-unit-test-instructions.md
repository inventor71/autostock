# F23 Unit Test Instructions

## Run All Tests
```bash
cd .claude/worktrees/F23
python -m pytest tests/ -v --tb=short
```

Expected: all 482 tests pass, 0 failures.

## Run F23-specific Tests Only
```bash
cd .claude/worktrees/F23
python -m pytest tests/test_signal_tools.py tests/test_multi_agent.py -v
```

Expected: 51 tests pass (30 signal tools + 21 multi-agent).

## Test Coverage by Module

### Signal Tools (test_signal_tools.py, 30 tests)
| Test Class | Tests | What It Covers |
|------------|-------|----------------|
| TestFundamentalsExtension | 2 | short interest keys present/missing |
| TestEarnings | 6 | calendar, lxml fallback, surprise history, errors, JSON |
| TestInsider | 3 | transactions, empty, JSON |
| TestAnalystUpgrades | 2 | upgrades list, empty |
| TestInstitutional | 2 | holders, empty |
| TestMacro | 3 | basic, partial failure, JSON |
| TestLessonRecord | 2 | round-trip, defaults |
| TestJournalLessons | 4 | append/read, next_id, increment, atomic |
| TestConfig | 5 | multi_agent defaults, timing, Settings fields, yaml |
| TestLessonCLI | 1 | CLI integration |

### Multi-Agent Orchestration (test_multi_agent.py, 21 tests)
| Test Class | Tests | What It Covers |
|------------|-------|----------------|
| TestOneShot | 4 | state file skip, normal state file, sub_agent factory, env override |
| TestMultiAgentPrompts | 7 | initial/debate/synthesis/sub_agent/parallel/reports/lesson |
| TestSequentialResearch | 2 | Mode B 3-round, Mode B N=2 minimal |
| TestParallelResearch | 2 | Mode C workspace isolation, fallback |
| TestDisabledFallback | 2 | disabled, N=1 fallback |
| TestTimeoutResolution | 2 | auto-calc, explicit override |
| TestSubAgentTask | 2 | task planning N=3, N=2 |

## Run with verbose failures only
```bash
python -m pytest tests/test_signal_tools.py tests/test_multi_agent.py --tb=long -q
```
