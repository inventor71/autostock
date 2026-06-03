# Unit 2: multi-agent-orchestration — NFR Design Patterns

## P1: Sub-agent Workspace Isolation (Mode C)

```python
def _create_isolated_workspace(journal: Journal) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="autostock_sub_"))
    for name in ("CLAUDE.md", "lessons.md", "regime.md", "watchlist.md"):
        src = journal.root / name
        if src.exists():
            shutil.copy2(src, tmp / name)
    if journal.positions_dir.exists():
        shutil.copytree(journal.positions_dir, tmp / "positions")
    return tmp
```

- 복사(copy), 심링크 아님 → agent가 resolve해서 원본에 쓸 위험 없음
- decisions.jsonl 미복사 → 구조적 쓰기 불가
- 완료 후 `shutil.rmtree(tmp, ignore_errors=True)`

## P2: AGENT_JOURNAL_ROOT Env Scrubbing

Sub-agent 세션의 `_invoke()` 에서:
```python
env = scrub_agent_env(dict(os.environ))
env["AGENT_JOURNAL_ROOT"] = str(isolated_workspace)  # override to temp
```

이렇게 하면 sub-agent의 `python -m src.agent.tools` 호출이 temp workspace를 사용.
기존 `watch set`, `lesson add` 등도 temp에만 영향.

## P3: One-Shot Session Mode

`AgentSession`에 `_one_shot: bool = False` 추가:

```python
def run_turn(self, ...):
    if self._one_shot:
        session_id = str(uuid.uuid4())
        resume = False
    else:
        # 기존 state file 로직
        ...
    
    payload = self._invoke(...)
    
    if not self._one_shot and not resume:
        self._write_state(session_id)
    
    return AgentTurnResult(...)
```

## P4: Research Timeout Resolution

`modes/agent.py`의 `_premarket_research()`:
```python
def _resolve_timeout(self) -> float:
    auto = (self.agent_cfg.research_start_before_open 
            - self.agent_cfg.research_end_before_open) * 60
    explicit = self.agent_cfg.research_timeout
    if explicit != 1800.0:
        logger.warning("research_timeout={:.0f}s overrides auto={:.0f}s", explicit, auto)
        return explicit
    return float(auto)
```

## P5: ThreadPoolExecutor for Mode C

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _run_parallel_research(self) -> AgentTurnResult:
    tasks = self._plan_sub_tasks()  # 기본 분배 또는 Manager planning
    sub_timeout = self._resolve_timeout() * 0.7  # sub-agent에 70% 할당, 나머지 synthesis
    
    reports = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(self._run_sub_agent, t, sub_timeout): t for t in tasks}
        for f in as_completed(futures, timeout=sub_timeout + 30):
            try:
                reports.append(f.result())
            except Exception as exc:
                task = futures[f]
                reports.append(SubAgentReport(
                    agent_index=task.agent_index, task=task,
                    result_text="", verdicts=[], completed=False, error=str(exc),
                ))
    
    # Synthesis (Manager, resumed session)
    return self._synthesize(reports)
```

## P6: Fail-Graceful Pipeline

```
try:
    multi-agent pipeline
except timeout/partial:
    use available results for synthesis
    if 0 decisions:
        fallback to single-session run_morning_research()
        log.warning("multi-agent fallback to single session")
```

## Concurrency Table (invariants)

| Thread | Reads | Writes | Lock |
|--------|-------|--------|------|
| _premarket_research (scheduler) | decisions.jsonl, journal files | decisions.jsonl (via Manager only) | turn_lock (try_scheduled_turn) |
| Mode C sub-agent (ThreadPool) | temp workspace (copied files), market data (yfinance) | 없음 (Write/Edit 미허용, temp workspace) | 없음 |
| Mode B debate rounds | decisions.jsonl, journal files (all in same session) | decisions.jsonl (synthesis only) | turn_lock 유지 |

Manager 세션만 원본 workspace에 쓰고, sub-agent는 temp에만 접근 → 동시 쓰기 경합 없음.
