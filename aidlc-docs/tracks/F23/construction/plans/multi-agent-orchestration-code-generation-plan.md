# Unit 2: multi-agent-orchestration — Code Generation Plan

## Step 0: 기존 코드 확인
- [x] orchestrator.py, session.py, prompts.py, modes/agent.py 구조 파악 완료

## Step 1: `AgentSession` 확장 — one_shot + create_sub_agent
- [ ] `_one_shot: bool = False` 속성 추가
- [ ] `run_turn()` — one_shot이면 state file skip, 항상 fresh uuid
- [ ] `create_sub_agent(workspace, model, timeout, runner)` 정적 팩토리
- [ ] `_invoke()` — one_shot이면 AGENT_JOURNAL_ROOT를 self.workspace로 override
- [ ] 테스트: one_shot 세션이 state file을 생성하지 않는지

## Step 2: `prompts.py` — 멀티에이전트 프롬프트 함수 추가
- [ ] `_build_signal_guide(signals: list[str]) -> str` — 활성 시그널 도구 가이드
- [ ] `_build_lesson_context(lessons: list[LessonRecord], max_n: int) -> str` — 최근 lesson 주입
- [ ] `multi_research_initial_prompt(universe, held, signals, lessons, n_rounds)` — Mode B Round 0
- [ ] `debate_prompt(round_num, total_rounds)` — Mode B debate round
- [ ] `synthesis_prompt(n_rounds)` — Mode B/C 최종 verdict
- [ ] `sub_agent_prompt(task_description, universe, signals)` — Mode C sub-agent
- [ ] 테스트: 프롬프트에 advisor reminder + verdict schema 포함 확인

## Step 3: `orchestrator.py` — 멀티에이전트 메서드 추가
- [ ] `_run_multi_research(run_fn)` — 공통 래퍼 (before/after decision count + turn_log)
- [ ] `_run_sequential_research(n_agents, timeout)` — Mode B: N-1 debate + synthesis
- [ ] `_run_parallel_research(n_agents, timeout)` — Mode C: sub-agent spawn + synthesis
- [ ] `_create_isolated_workspace() -> Path` — temp dir + 파일 복사
- [ ] `_run_sub_agent(task, workspace, timeout) -> SubAgentReport` — 단일 sub-agent 실행
- [ ] `_plan_sub_tasks(n_agents) -> list[SubAgentTask]` — 기본 업무 분배
- [ ] `run_morning_research()` 수정 — config 분기
- [ ] 테스트: Mode B/C 각 mock runner로 흐름 검증

## Step 4: `modes/agent.py` — timeout 계산 + 분기
- [ ] `_resolve_research_timeout() -> float` — auto-calc vs explicit override
- [ ] `_premarket_research()` — MultiAgentConfig 읽어서 orchestrator에 전달
- [ ] 기존 `research_hour`/`research_minute` → `research_start_before_open` 기반 계산
- [ ] 테스트: timeout 계산 (auto, override, 기본값)

## Step 5: 통합 테스트 + 회귀
- [ ] Mode B end-to-end (mock runner, 3 rounds, decision counting)
- [ ] Mode C end-to-end (mock runner, 2 sub-agents, isolated workspace verification)
- [ ] enabled=false 폴백 (기존 경로 동일)
- [ ] N=1 + enabled=true → 폴백
- [ ] timeout/deadline 테스트
- [ ] 기존 전체 회귀 테스트 통과

## 변경 파일
| 파일 | 변경 |
|------|------|
| `src/agent/session.py` | _one_shot + create_sub_agent + env override |
| `src/agent/prompts.py` | 5개 새 프롬프트 함수 + signal_guide + lesson_context |
| `src/agent/orchestrator.py` | run_morning_research 분기 + sequential/parallel + helpers |
| `src/trading/modes/agent.py` | _resolve_research_timeout + _premarket_research 수정 |
| `tests/test_multi_agent.py` | 통합 테스트 |
