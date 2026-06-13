# U2 Functional Design — eval harness

## 코드 확인으로 정해진 사실 (구현 전제)
- 실행 루프 클래스명은 `AgentTradingLoop`(설계 문서의 "OrchestratorAgent"는 가칭).
  ctor 필수 = `session` + `universe`. broker 불필요.
- `AgentSession._invoke`는 `os.environ`(scrub 후)을 승계하고 **one_shot이면
  `AGENT_JOURNAL_ROOT=workspace`를 자동 설정** (`session.py:215-217`) — fixture env는
  provider 프로세스의 os.environ에 넣으면 tool subprocess까지 전파.
- guidance = `build_guidance(history)` = 코드 상수 `AGENT_CONSTITUTION` + history의
  evolved_section — sandbox `guidance/history.json` 주입으로 버전 통제 (`self_rewrite.py:75-99`).
- intraday/wake/eod turn은 lessons recall(_get_lessons)을 타지 않음(research 전용) —
  단 `reflection_enabled=False`로 명시해 네트워크 경로(collect_outcomes)를 구조적으로 차단.
- executor replay 의존: `data_provider.get_latest_price()`(`executor.py:266`) →
  시나리오의 명시적 `prices` 맵으로 충족. ATR 경로(get_bars)는 stop 포함 시나리오에선 미사용.

## 설계 정제 (R2): Expectation의 (action,side) → allowed_actions
시나리오 작성자가 보유 side를 알고 작성하므로 허용 집합은 액션 리스트로 평탄화
(short 보유 시나리오에만 BUY_TO_COVER를 나열). no_churn=True는 "새 결정 없음 또는
HOLD-carry만"으로 정의 (HOLD+stop은 보호 주문 유지라 churn이 아님).

## 모듈
- `src/evals/scenario.py`: `Scenario`/`Expectation` (pydantic v2) + load/save. PBT-02 round-trip.
- `src/evals/sandbox.py`: `build_sandbox(scenario, guidance_history=None)` → 임시 workspace
  (CLAUDE.md 템플릿 + workspace fixture + decisions 히스토리 + guidance) + fixture dir 생성;
  `run_scenario_turn(...)` → env 설정 + AgentTradingLoop one_shot turn 디스패치.
- `src/evals/artifacts.py`: `TurnArtifacts` — 신규 결정(스탬프 포함), thesis diff, 응답 텍스트,
  raw 라인 수 delta(추출 무결성용).
- `src/evals/grading.py`: `grade_tier1(scenario, artifacts, ...)` — hard(스키마/추출 무결성),
  behavior(allowed_actions 매칭, no_churn, lessons_cited 인용률 — 측정만), executor replay
  (SimulatedBroker(보유 시드) + RiskManager(use_bracket_orders=True) + FixturePriceProvider).
  PBT-03: 매칭 불변식.
- `evals/provider.py`: promptfoo python provider `call_api` → 파이프라인 실행, 출력 JSON.
- `evals/promptfooconfig.yaml`(Tier-1 hard assert만) / `promptfooconfig.tier2.yaml`(llm-rubric).
- `evals/rubrics/{intraday,wake,eod}.md`, `evals/workspace_template/CLAUDE.md`(운영 사본 박제),
  `evals/package.json`(promptfoo 고정).

## 토큰-0 검증 전략
`_FakeRunner` 패턴(tests/test_agent.py)으로 end-to-end: fake runner가 sandbox
decisions.jsonl에 결정을 직접 append(에이전트의 Write를 모사)하고 응답 JSON 반환 →
guidance 주입(수용 기준 7)은 runner가 받은 prompt(input)에 버전 문구 포함 여부로 검증.
