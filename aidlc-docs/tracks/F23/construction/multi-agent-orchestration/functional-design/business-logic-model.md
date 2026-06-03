# Unit 2: multi-agent-orchestration — Business Logic Model

## BLM-1: 멀티에이전트 Research Turn 전체 흐름

`run_morning_research()`가 분기점. `multi_agent.enabled`에 따라:

```
enabled=false → 기존 단일 _run() (현재 코드 그대로)
enabled=true  → mode 에 따라:
  sequential → _run_sequential_research() (Mode B)
  parallel   → _run_parallel_research()   (Mode C)
```

### Mode B — Sequential Debate (단일 세션, N-1 라운드)

하나의 `claude -p` 세션 안에서 N-1번 debate turn + 1번 synthesis turn.
세션이 resumed되므로 컨텍스트가 누적됨.

```
_run_multi_research() wraps:
  before = len(journal.read_decisions())
  
  # Round 0: initial research (기존 morning_research_prompt과 유사)
  session.run_turn(initial_research_prompt, model=research_model)
  
  # Round 1..N-2: debate rounds (resumed session)
  for i in range(1, n_agents - 1):
    session.run_turn(debate_prompt(round=i, total=n_agents-1))
  
  # Final: synthesis/verdict (resumed session)
  session.run_turn(synthesis_prompt)
  
  after decisions = journal.read_decisions()[before:]
  # decision counting은 전체 debate를 하나의 research turn으로 캡처
```

핵심 제약:
- 모든 라운드가 하나의 `_run()` 래퍼 안 → decision count가 최종 verdict만이 아니라 중간 라운드의
  결정도 포함할 수 있음. Synthesis prompt에서 "이전 라운드의 탐색적 결정을 대체하라" 지시 필요.
- `turn_log.record_turn()`은 마지막 라운드의 raw만 기록. 중간 라운드는 별도 로깅하지 않음
  (세션 컨텍스트에 누적되어 있으므로 디버그 시 세션 replay로 확인).

### Mode C — Parallel Sub-agents (멀티 세션, 격리 workspace)

Manager 세션이 N-1개 sub-agent를 병렬 spawn 후 종합.

```
_run_parallel_research() wraps:
  before = len(journal.read_decisions())
  
  # Phase 1: Manager가 작업 분배 계획 수립
  plan_result = session.run_turn(planning_prompt, model=research_model)
  # plan_result.result에서 sub-agent별 task 추출 (또는 기본 분배)
  
  # Phase 2: N-1 sub-agents 병렬 launch (격리 workspace)
  reports = []
  with ThreadPoolExecutor(max_workers=n_agents-1) as pool:
    futures = [pool.submit(_run_sub_agent, task, isolated_workspace) for task in tasks]
    for f in as_completed(futures, timeout=sub_timeout):
      reports.append(f.result())  # AgentTurnResult.result (stdout text)
  
  # Phase 3: Manager synthesis (resumed session)
  session.run_turn(synthesis_prompt(reports), model=research_model)
  
  after decisions = journal.read_decisions()[before:]
```

Sub-agent 격리 (NFR-4):
- 임시 workspace (`tempfile.mkdtemp`)에 읽기용 파일 복사/심링크
- `allowed_tools` = 읽기 전용 (`Read`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Bash(python -m src.agent.tools:*)`)
  — `Write`/`Edit` 미포함
- `AGENT_JOURNAL_ROOT` env를 temp workspace로 override
- fresh session_id (state file 사용 안 함)
- 결과는 stdout JSON `result` 필드로 반환

## BLM-2: 프롬프트 설계

### 공통 컨텍스트 (모든 모드)
- 날짜, universe, held symbols, advisor reminder
- `research.signals` 목록에 따라 사용 가능한 도구 가이드 주입
- `research.reflection.enabled`이면 최근 N개 lesson 주입

### Mode B 프롬프트 시퀀스

**Round 0 (Initial Research)**:
```
기존 morning_research_prompt + 추가 지시:
"이 분석은 {N-1}개 후속 토론 라운드 중 첫 번째입니다.
 지금은 데이터를 수집하고 초기 판단을 내리세요.
 결론은 아직 decisions.jsonl에 기록하지 마세요 — 최종 라운드에서만 기록합니다."
```

**Round 1..N-2 (Debate)**:
```
"토론 라운드 {i}/{N-1}.
 이전 라운드의 분석을 비판적으로 평가하세요.
 - 놓친 리스크나 기회가 있는가?
 - 데이터 해석이 편향되지 않았는가?
 - 시장 레짐 판단이 현재 조건과 일치하는가?
 반대 관점에서 반론을 제시하고, 추가 데이터가 필요하면 도구로 확인하세요.
 decisions.jsonl에 기록하지 마세요."
```

**Final Round (Synthesis)**:
```
"최종 종합 라운드.
 이전 {N-1}개 라운드의 분석과 토론을 종합하여 최종 판단을 내리세요.
 각 종목에 대해:
 1. 이전 라운드에서 제기된 bull/bear 근거를 모두 고려
 2. 최종 결정(BUY/SELL/HOLD/ADJUST_STOP)을 decisions.jsonl에 기록
 3. 아래 Verdict 형식으로 구조화된 결론도 작성

 ## Verdict
 - symbol: <TICKER>
 - action: BUY | SELL | HOLD | ADJUST_STOP
 - confidence: 0.0-1.0
 - stop: <price>
 - target: <price>
 - reason: <one-line>

 {_ADVISOR_REMINDER}"
```

### Mode C 프롬프트

**Planning Prompt (Manager)**:
```
"이 research turn에서 {N-1}명의 독립 분석가가 병렬로 작업합니다.
 각 분석가에게 맡길 업무를 구분하세요:
 - 가용 도구: {enabled_signals 기반 도구 목록}
 - Universe: {universe}
 - 현재 보유: {held}
 각 분석가의 업무를 1-2문장으로 기술하세요."
```

(Planning은 선택적 — 기본 분배 전략으로 대체 가능: 분석가 1=held positions review,
분석가 2=discovery/scoreboard, 등)

**Sub-agent Prompt**:
```
"당신은 PM 트레이딩 에이전트의 독립 분석가입니다.
 담당 업무: {task_description}
 가용 도구: {tool_list}
 Universe: {universe}

 분석 결과를 자유 텍스트로 작성하되, 마지막에 반드시 아래 형식의 Verdict 섹션을 포함하세요:

 ## Verdict
 (종목별로)
 - symbol: ...
 - action: ...
 - confidence: ...
 - reason: ...

 decisions.jsonl에 기록하지 마세요 — 최종 결정은 Manager가 내립니다.
 {_ADVISOR_REMINDER}"
```

**Synthesis Prompt (Manager, resumed)**:
```
"아래는 {N-1}명 분석가의 독립 보고서입니다:

 --- 분석가 1 ---
 {report_1}
 --- 분석가 2 ---
 {report_2}
 ...

 이들의 분석을 종합하여 최종 판단을 내리세요. 교차 검증:
 - 다수가 동의하는 판단은 신뢰도를 높이세요
 - 분석가 간 불일치가 있으면 추가 데이터를 확인하세요
 - 최종 결정을 decisions.jsonl에 기록하세요
 - Verdict 형식으로 구조화된 결론을 작성하세요

 {verdict_schema}
 {_ADVISOR_REMINDER}"
```

## BLM-3: Research Timeout 계산 + 하위 호환

```python
def _resolve_research_timeout(agent_cfg: AgentConfig) -> float:
    auto = (agent_cfg.research_start_before_open - agent_cfg.research_end_before_open) * 60
    explicit = agent_cfg.research_timeout
    # 명시값(1800 기본)이 auto와 다르면 → 사용자가 의도적으로 설정한 것
    # 기본값(1800)과 같으면 → auto 사용
    if explicit != 1800.0:
        logger.warning("research_timeout={} overrides auto-calculated {}s", explicit, auto)
        return explicit
    return float(auto)
```

기존 `research_timeout: 1800`이 설정 파일에 있는 경우:
- `1800 == AgentConfig.research_timeout` 기본값이므로 auto-calculated 값(3300)이 사용됨
- 사용자가 의도적으로 다른 값(예: 2400)을 넣었으면 그 값이 우선

## BLM-4: AgentSession 확장 — one_shot 모드

Mode C sub-agent용 세션 팩토리:

```python
@staticmethod
def create_sub_agent(
    workspace: Path,
    model: str = "sonnet",
    timeout: float = 600.0,
    runner: Callable | None = None,
) -> AgentSession:
    """격리된 sub-agent 세션 (Mode C). 읽기 전용 도구만, state file 없음."""
    READ_ONLY_TOOLS = [
        "Read", "Glob", "Grep", "WebSearch", "WebFetch",
        "Bash(python -m src.agent.tools:*)",
        "Bash(python3 -m src.agent.tools:*)",
    ]
    session = AgentSession(
        workspace=workspace,
        model=model,
        allowed_tools=READ_ONLY_TOOLS,
        timeout=timeout,
        runner=runner,
    )
    # state file을 사용하지 않도록 override (항상 fresh session)
    session._fixed_date = None
    session._one_shot = True
    return session
```

`_one_shot=True`일 때 `run_turn()`:
- `_read_state()` 스킵 → 항상 fresh uuid
- `_write_state()` 스킵 → state file 미생성
- env에서 `AGENT_JOURNAL_ROOT`를 temp workspace로 override

## BLM-5: 격리 Workspace 생성/정리

```python
def _create_isolated_workspace(source_journal: Journal) -> Path:
    """Mode C sub-agent용 읽기 전용 workspace 생성."""
    tmp = Path(tempfile.mkdtemp(prefix="autostock_subagent_"))
    # 읽기 참조 파일 복사 (심링크는 agent가 resolve해서 원본에 쓸 위험)
    for name in ("CLAUDE.md", "lessons.md", "regime.md", "watchlist.md"):
        src = source_journal.root / name
        if src.exists():
            shutil.copy2(src, tmp / name)
    # positions/ 디렉토리 복사
    pos_src = source_journal.positions_dir
    if pos_src.exists():
        shutil.copytree(pos_src, tmp / "positions")
    # decisions.jsonl은 의도적으로 복사하지 않음 (sub-agent가 쓸 수 없어야 함)
    return tmp
```

정리: sub-agent 완료 후 `shutil.rmtree(tmp)`.

## BLM-6: Fail-Graceful Hard Deadline

pre-market research가 `research_end_before_open` 분 전까지 완료되지 않을 경우:

- Mode B: subprocess timeout이 자연 종료 → 마지막 완료된 라운드까지의 결과로 synthesis 시도
  (synthesis 전 timeout이면 → 이전 라운드의 결정 사용)
- Mode C: `futures` timeout → 완료된 sub-agent 보고서만으로 synthesis.
  미완료 sub-agent는 무시, 로그 경고.
- 모든 경우: decisions.jsonl에 최소 1개 결정이라도 있으면 정상 진행.
  0개이면 → fallback: 기존 단일 세션 `run_morning_research()` 1회 시도 (마지막 방어선).
