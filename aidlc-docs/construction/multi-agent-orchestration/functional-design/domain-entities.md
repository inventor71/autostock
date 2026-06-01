# Unit 2: multi-agent-orchestration — Domain Entities

## 기존 엔티티 (변경 없음, 재사용)

| 엔티티 | 위치 | 역할 |
|--------|------|------|
| `Decision` | `journal.py` | decisions.jsonl 행. 불변. |
| `AgentTurnResult` | `session.py` | turn 결과 (result, session_id, raw). 불변. |
| `AgentSession` | `session.py` | claude -p 세션 래퍼. **확장** (아래). |
| `AgentTradingLoop` | `orchestrator.py` | 턴 시퀀서. **확장** (아래). |
| `Journal` | `journal.py` | workspace 파일 접근. Unit 1에서 LessonRecord 추가됨. |
| `LessonRecord` | `journal.py` | F23 Unit 1에서 추가. 불변. |

## 새 엔티티

### E1: `MultiAgentConfig` (Unit 1에서 이미 추가)
`config/config.py`. `enabled`, `mode`, `n_agents`.

### E2: `SubAgentTask`
Sub-agent에게 할당할 업무 기술. Mode C에서만 사용.

```python
@dataclass
class SubAgentTask:
    agent_index: int       # 0-based
    description: str       # 자연어 업무 기술
    focus_symbols: list[str] = field(default_factory=list)  # 선택적 집중 종목
```

Manager의 planning turn 결과에서 추출되거나, 기본 분배 전략에서 생성.

### E3: `SubAgentReport`
Sub-agent의 분석 결과.

```python
@dataclass
class SubAgentReport:
    agent_index: int
    task: SubAgentTask
    result_text: str       # stdout의 result 필드
    verdicts: list[dict]   # Verdict 섹션 파싱 결과 (best-effort)
    completed: bool        # timeout 전 완료 여부
    error: str | None = None
```

### E4: 확장 — `AgentSession._one_shot`
기존 `AgentSession`에 `_one_shot: bool = False` 속성 추가.
True이면 state file 읽기/쓰기를 건너뛰고 매 turn 새 UUID.

### E5: 확장 — `AgentTradingLoop` 멀티에이전트 메서드
`run_morning_research()`가 config 분기 → `_run_sequential_research()` 또는 `_run_parallel_research()` 호출.

## 변경 대상 모듈 (Unit 2)

| 모듈 | 변경 |
|------|------|
| `src/agent/orchestrator.py` | `run_morning_research()` 분기 + `_run_sequential_research()` + `_run_parallel_research()` + 헬퍼 |
| `src/agent/session.py` | `_one_shot` 플래그 + `create_sub_agent()` 팩토리 + env 스크러빙 |
| `src/agent/prompts.py` | debate/synthesis/sub-agent/planning 프롬프트 함수 |
| `src/trading/modes/agent.py` | `_premarket_research()` timeout 계산 + 멀티에이전트 분기 |
| `config/config.py` | (Unit 1에서 완료, 추가 변경 없음) |
