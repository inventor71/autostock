# Unit 2: multi-agent-orchestration — NFR Requirements

## 결론: 0 new runtime dependencies

기존 stdlib (`tempfile`, `shutil`, `concurrent.futures`, `threading`) + 프로젝트 의존성 (pydantic, loguru, APScheduler) 재사용. 새 런타임 의존성 없음.

## NFR-1: 세션 격리 (Mode C)
- Sub-agent 프로세스는 원본 workspace에 쓸 수 없어야 함 (structural guarantee)
- 구현: temp dir + 읽기 전용 allowed_tools + AGENT_JOURNAL_ROOT override
- 검증: sub-agent가 Write/Edit 시도 시 claude CLI가 거부하는지 확인 (통합 테스트)

## NFR-2: Timeout / Hard Deadline
- auto-calculated: `(start_before_open - end_before_open) * 60`
- subprocess timeout으로 강제 (기존 `session.run_turn` 경로)
- Mode C: `ThreadPoolExecutor` timeout으로 sub-agent 일괄 종료

## NFR-3: 비용 제한
- Mode B: 단일 세션이므로 ~1.5-2× (더 긴 컨텍스트)
- Mode C: N 세션 = N× 비용. N=3 기본 → 3×. 병렬이라 wall-clock은 비슷.
- 제어: `n_agents` 상한 5, `enabled=false` 토글

## NFR-4: Advisor-Only 보존
- 멀티에이전트에서도 어떤 agent도 직접 주문하지 않음
- decisions.jsonl → DecisionExecutor → RiskManager → Broker 경로 불변
- Sub-agent는 decisions.jsonl에 접근 불가 (workspace에 미포함)

## NFR-5: 기존 경로 무중단
- `multi_agent.enabled=false`이면 기존 `run_morning_research()` 정확히 동일
- 멀티에이전트 코드가 기존 import path에 side-effect 없음
- 기존 테스트 전부 통과
