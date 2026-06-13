# F74 Application Design — Prompt Eval & Regression Framework

## 1. 컴포넌트 개요

```text
+---------------------------------------------------------------+
|                      evals/  (promptfoo 글루)                  |
|  promptfooconfig.yaml   provider.py   rubrics/   scenarios/   |
|  package.json (promptfoo 고정버전, bun 실행)                    |
+------------------------------+--------------------------------+
                               |  imports
+------------------------------v--------------------------------+
|                src/evals/  (파이썬 코어 — pytest/PBT 대상)      |
|  scenario.py   sandbox.py   artifacts.py   grading.py         |
|  extract.py (CLI)                                             |
+----+--------------------+--------------------+----------------+
     | builds tmp ws      | runs turn          | replays
+----v-----------+  +-----v------------+  +----v---------------+
| workspace tmpl |  | OrchestratorAgent|  | DecisionExecutor   |
| (evals 내 박제) |  | + AgentSession   |  | + SimulatedBroker  |
+----------------+  |   (one_shot)     |  | + RiskManager      |
                    +-----+------------+  |   (bracket)        |
                          | subprocess     +--------------------+
                    +-----v------------+
                    | python -m        |
                    |  src.agent.tools |
                    |  (fixture mode)  |
                    +------------------+
```

(텍스트 대안: evals/의 promptfoo가 provider.py를 호출 → provider는 src/evals/ 코어를 import
→ 코어가 임시 workspace를 만들고 OrchestratorAgent로 turn 실행 → turn 중 agent가 subprocess로
`python -m src.agent.tools`를 부르면 fixture 모드가 시나리오 JSON으로 응답 → 코어가 산출물을
추출해 Tier-1 채점(실제 DecisionExecutor 리플레이 포함) 후 promptfoo에 구조화 출력 반환.)

## 2. 컴포넌트 정의

### C1. DataSources 팩토리 — `src/agent/tools/sources.py` (신규)
- `DataSources`: price_provider / broker_factory / news_provider / ticker_factory /
  signal_collector_factory를 묶는 경량 컨테이너 (FR-1의 "단일 주입 팩토리").
- `default_sources() -> DataSources`: 현 프로덕션 결선 그대로 (YFinanceProvider,
  AlpacaBroker, YFinanceNewsProvider, `yfinance.Ticker`, SignalCollector).
- `resolve_sources() -> DataSources`: env `AUTOSTOCK_TOOLS_FIXTURE_DIR` 설정 시
  `fixture_sources(dir)`, 아니면 `default_sources()`. `__main__.py`가 시작 시 1회 호출.
- `__main__.py`의 13개 디스패치가 전부 sources의 의존을 **명시 인자로** `market.*`에 전달
  (현재 인자 없는 8개 명령은 `market.py` 함수 시그니처에 provider/ticker_factory 파라미터
  추가 — 기본값 유지로 기존 직접 호출 호환).
- **record 모드** (v1 포함, 저렴): env `AUTOSTOCK_TOOLS_RECORD_DIR` 설정 시
  `RecordingSources`로 감싸 실 응답을 tool별 JSON으로 캡처 — 이후 실사건의 자동 박제 소스.
  (FR-3 수동 보강 비용의 장기 해소책)

### C2. Fixture 소스 — `src/agent/tools/fixture_sources.py` (신규)
- 시나리오의 `tools/` fixture JSON을 읽어 DataSources 인터페이스로 응답.
- fail-honest: 미정의 (tool, symbol) 키 → 구조화 에러 응답
  `{"error": "fixture_missing", "tool": ..., "symbol": ...}` (조용한 실데이터 폴백 금지).
- src/ 안에 두는 이유: agent의 tool 호출은 **subprocess**(`python -m src.agent.tools`)라
  evals/ 밖에서도 import 가능해야 함.

### C3. 시나리오 스키마 — `src/evals/scenario.py` (신규, pydantic)
- `Scenario`: id, turn_type(wake|intraday|eod), origin(lesson/실사건 메타), brief/trigger 입력,
  `tool_fixtures`(명령→심볼→응답), `workspace_fixture`(positions/*.md, lessons.md, regime.md,
  watchlist.md, decisions.jsonl 히스토리), `expectation`, `rubric_refs`.
- `Expectation`: 허용 (action, side) 집합 + no-churn 플래그 + 메모. (FR-2)
- 직렬화 round-trip + 매칭 불변식 = **PBT-02/03 대상** (도메인 제너레이터는
  `tests/evals/generators.py`에 중앙화 — PBT-07).

### C4. Sandbox 빌더 — `src/evals/sandbox.py` (신규)
- 임시 workspace 구성: `evals/workspace_template/CLAUDE.md`(git 박제 — 운영 `workspace/`는
  **전부 gitignore**라 eval 전용 사본을 리뷰해 커밋) + 시나리오 workspace_fixture 전개 +
  `guidance/history.json`에 **요청된 guidance 버전 주입** (orchestrator의
  `load_history(journal.root)`가 읽음 — 코드 확인). `.sessions/` 미생성.
- turn 실행: `OrchestratorAgent(session=AgentSession(workspace=tmp, one_shot=True), universe=시나리오 universe)`
  → turn_type별 `run_intraday(brief)` / `run_wake(brief, events)` / `run_eod_review(outcomes)`.
- subprocess 환경: `AUTOSTOCK_TOOLS_FIXTURE_DIR`를 turn 실행 환경에 주입.
- **주의 2건 (코드 확인)**: ① guidance preamble은 research/intraday/wake turn에만 prepend
  (`orchestrator.py:146-150`) — EOD는 프로덕션도 미주입이므로 **guidance matrix는
  intraday/wake 시나리오에만 적용**, EOD는 단일 버전 평가. ② `run_eod_review`는
  `_run_self_rewrite()`를 호출하지만 `_rewrite_fn` 미설정(None) 시 inert — sandbox에서
  rewrite를 설정하지 않는다.

### C5. 산출물 추출 — `src/evals/artifacts.py` (신규)
- turn 전후 `journal.read_decisions()` 차분(torn-write-safe 선례 패턴), thesis 파일 diff,
  응답 텍스트, 토큰/비용 메타 → `TurnArtifacts` (구조화).
- `prompt_version`은 orchestrator `_stamp_new`가 스탬프(경유 전제 충족) — matrix 축 검증에 사용.

### C6. Tier-1 채점 — `src/evals/grading.py` (신규)
- **hard**: Decision 스키마 적합성, 추출 무결성.
- **non-blocking**: expectation (action,side) 매칭, no-churn 위반, lessons_cited 인용률(측정만).
- **executor-replay**: `DecisionExecutor(broker=SimulatedBroker, risk_manager=RiskManager(use_bracket_orders=True),
  data_provider=fixture, universe=시나리오)` → 결정별 `execute_decision(d)` →
  `ExecutionOutcome.status` 수집. (FR-5 — `execute_pending` 금지)

### C7. promptfoo 글루 — `evals/` (신규)
- `provider.py`: promptfoo Python provider 계약(`call_api(prompt, options, context)`) —
  context의 vars(scenario_id, guidance_version, run_id)로 C4→C5→C6 파이프라인 실행,
  `{"output": <TurnArtifacts+grades JSON>}` 반환.
- `promptfooconfig.yaml`: tests = 시나리오 매트릭스, asserts = ①python assert(Tier-1 결과
  참조) ②`llm-rubric`(Tier-2, `evals/rubrics/<turn_type>.md`) — Tier-2는 별도 config
  (`promptfooconfig.tier2.yaml`)로 분리해 on-demand만.
- `package.json`: promptfoo 고정 버전 devDependency, 실행은 bun
  (`cd evals && bun install && bun run eval`) — bun 툴체인 기존 존재(operator-console).
- concurrency cap: promptfoo `maxConcurrency` 설정 (구독 rate limit).

### C8. 추출기 — `src/evals/extract.py` (신규, CLI)
- `python -m src.evals.extract --date 2026-06-08 --symbol AAPL --turn-type intraday`
- 자동: 보유/체결(decisions+execution_outcomes), 계좌(equity.jsonl), 가격 bars+지표 재계산,
  intraday features(있으면). 수동: 뉴스/펀더멘털 등 → `"TODO_MANUAL"` 마커 생성. (FR-3)

## 3. 의존 방향
`evals/`(글루) → `src/evals/`(코어) → `src/agent/`(orchestrator/session/journal/executor,
무수정) + `src/agent/tools/sources.py`(신규 seam) + `src/risk/`,`src/execution/`(무수정).
역방향 의존 없음 — `src/agent/`는 `src/evals/`를 모른다 (sources.py의 env 분기만 접점).

## 4. 설계 결정 (본 단계에서 확정)
| # | 결정 | 근거 |
|---|---|---|
| D1 | 코어 로직은 `src/evals/`, 글루는 `evals/` | pytest/PBT 수집 경로(src 미러링, R13 방향)와 promptfoo workspace 분리 |
| D2 | promptfoo는 `evals/package.json` 고정 버전 + bun 실행 | 재현성 + 기존 bun 툴체인, 루트 Python 의존성 무영향 (NFR-5) |
| D3 | record 모드 v1 포함 | C1에 데코레이터 1개 — 미래 시나리오 자동 박제로 FR-3 수동 비용 해소 |
| D4 | guidance matrix는 intraday/wake 한정 | EOD는 프로덕션도 guidance 미주입 (`orchestrator.py:146-150`) |
| D5 | workspace 템플릿은 `evals/workspace_template/` git 박제 | 운영 workspace/ 전부 gitignore — 추적 사본 필요 |
| D6 | judge 모델 기본 = Claude (promptfoo가 ANTHROPIC_API_KEY로 자동 선택), 루브릭에서 모델 고정 가능 | wrapper 0줄 (조사 확인) |

## 5. Extension Compliance
- Security Baseline: Disabled (N/A)
- PBT Partial: PBT-09 충족(hypothesis 기존 의존성·문서화), PBT-02/03/07/08은 C3
  (scenario round-trip, expectation 매칭 불변식, 중앙 제너레이터, seed/shrinking 기본) —
  U1/U2 Functional Design에서 구체 테스트 명세.
