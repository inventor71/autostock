# F74 — Prompt Eval & Regression Framework: 요구사항 (Requirements)

## 1. 의도 분석 (Intent Analysis)

- **사용자 요청 (원문)**: "다양한 부분에서 prompt에 따라서 ai가 대답을 할텐데, agent에 다양한
  synthetic data를 넘기면서 대답의 quality를 체크할 수 있는 파이프라인이 있으면 이걸 평가 할 수
  있을거 같은데. 이런 용도의 오픈소스 add-on을 달아서 prompt 자동 평가를 할 수 있을지 찾아보고,
  마땅한게 없다면 만들어서 확인해보자" → 조사 결과 promptfoo 채택 결정(사용자 확인), 비전 수립
  → /critic 검토 6건 반영 → "위 내용대로 열고 진행"
- **요청 유형**: 신규 기능 (내부 개발/품질 도구 — 평가 인프라)
- **스코프 추정**: 중간 — 신규 `evals/` 디렉터리 + `src/agent/tools/__main__.py` 팩토리
  리팩터링 + FakeBroker + 추출 스크립트. 프로덕션 거래 경로 변경 없음.
- **복잡도 추정**: 중상 — LLM 비결정성, 세션 격리, fixture 표면적(13개 tool)이 본질적 난점.
  단 critic 라운드로 리스크가 사전 식별되어 설계 불확실성은 낮음.
- **깊이**: Standard (사전 대화에서 핵심 결정 완료, 본 문서는 그 확정 사항의 정식화)

## 2. 배경 / 문제 정의

agent의 행동 품질은 프롬프트(`src/agent/prompts.py`), workspace `CLAUDE.md`, F64 EVOLVABLE
GUIDANCE(`workspace/guidance/history.json`)에 의해 결정되는데, 이들이 바뀔 때(사람 수정 또는
F64 self-rewrite) 과거에 올바르게 처리했던 상황을 여전히 올바르게 처리하는지 검증할 방법이
없다. lessons.md의 교훈은 프롬프트에 주입되는 텍스트일 뿐, 행동으로 검증되지 않는다.
F61 Tier-2 harness(`src/signals/eval_readthrough.py`)가 선례지만 signals 경로 한정 +
채점이 수동(사람 눈)이다.

**목표**: 실전 교훈을 동결된 합성 시나리오로 박제하고, agent의 실제 turn 행동
(decisions.jsonl 산출물)을 자동 채점하는 회귀 평가 파이프라인.

## 3. 기능 요구사항 (FR)

### FR-1: Fixture Provider 팩토리 (tools 리팩터링)
- `src/agent/tools/__main__.py`의 데이터 소스 결선을 **단일 주입 팩토리**로 통합한다.
  주입 가능한 seam이 이미 있는 명령(`_provider()`: quote/indicators/scoreboard,
  `_broker()`: account, `_signal_collector()`: movers/readthrough/earnings_calendar)뿐 아니라,
  **현재 주입 인자 없이 디스패치되는 8개 명령**(fundamentals/short_data/news/earnings/insider/
  analyst_upgrades/institutional/macro — `__main__.py:125-149`, `market.py` 내부에서
  `yfinance.Ticker`/`YFinanceNewsProvider`를 자체 생성)에 **ticker_factory/news_provider/macro
  소스 seam을 신설**하여 전부 팩토리를 경유시킨다 (critic 2라운드 MEDIUM-1).
- fixture 모드 활성화 시(환경변수로 fixture 디렉터리 지정) 13개 tool 명령이 시나리오 JSON에서
  응답한다. **fixture 계약 문서**가 각 명령의 응답 스키마를 명세한다.
- **보유 상태 fixture가 1순위**: 보유 포지션(qty/side/avg_entry), resting orders(stop/target),
  계좌(equity/cash), fills를 시나리오가 정의하고 `account` tool이 반환한다. 브로커 구현은
  신규 FakeBroker 제작보다 **기존 `SimulatedBroker` 재사용을 우선 검토**한다 (bracket/OCO
  지원 + `is_market_open()=True` 상속 — critic 2라운드 MEDIUM-2).
- 미정의 fixture 키 접근은 **fail-honest**(명시적 에러 응답, 조용한 실데이터 폴백 금지).
  시나리오는 해당 turn에서 agent가 부를 법한 tool의 fixture를 갖춰야 하며, 에러 응답을 받은
  agent의 거동(우회/중단)도 루브릭 관찰 대상이다.

### FR-2: 시나리오 포맷
- JSON 1파일 = 1시나리오: `evals/scenarios/{wake,intraday,eod}/<id>.json`
- 구성: (a) turn 타입 + 트리거/브리프 입력, (b) 시장 fixture(가격/지표/뉴스/펀더멘털),
  (c) workspace fixture(thesis 파일들, lessons.md, regime.md, watchlist.md, decisions.jsonl
  히스토리 — `.sessions/`는 **제외**), (d) 기대행동 = **(action, side) 허용 집합**
  (예: 선제 청산 = `SELL(sell_pct=1.0)` | `ADJUST_STOP`(타이트닝) | short이면 `BUY_TO_COVER`)
  + no-churn 기대(액션 없음이 정답인 시나리오), (e) Tier-2 루브릭 참조, (f) 메타(기원
  lesson/실사건, 작성일).

### FR-3: 기록 데이터 추출 스크립트 — 골격 추출 + 수동 보강 (critic 2라운드 HIGH-1로 재조정)
> ⚠️ **사용자 결정("추출 우선")의 현실 제약**: 운영 기록에는 시나리오 전체를 채울 데이터가
> 존재하지 않음이 코드 검증으로 확인됐다 — `turns.jsonl`은 메타데이터만(프롬프트/응답/툴호출
> 미보존), 뉴스 헤드라인은 `.news_seen.json`에 심볼당 마지막 1건만(히스토리 없음),
> fundamentals/insider/analyst/institutional/macro는 어떤 기록도 없음. 따라서 "전자동 추출"은
> 불가능하며 **추출기는 골격(재구성 가능한 슬라이스)을 생성하고 나머지는 수동 보강**한다.
- **추출기가 자동으로 채우는 것**: 보유 포지션·체결 이력(decisions.jsonl +
  execution_outcomes.jsonl), 계좌 스냅샷(equity.jsonl), 과거 가격 bars 및 그로부터 재계산한
  indicators(yfinance 과거 데이터 — 조회 가능 기간 내), intraday features(수집된 심볼·날짜
  한정, `src/data/intraday/store.py`).
- **수동 보강이 필요한 것(추출기가 TODO 마커로 표시)**: 뉴스 헤드라인, fundamentals,
  insider/analyst/institutional/macro. 보강 시 1차 소스 = **positions/*.md Call-vs-Outcome
  로그**(당시 헤드라인·이벤트가 서술로 풍부히 인용됨)와 lessons.md, 2차 = 웹 아카이브.
- v1 코퍼스 목표 동일: lesson #17(AAPL WWDC 선제청산), #16(AVGO 캐스케이드 방어),
  #15(중복 헤드라인 no-churn), 무트리거 조용한 날(no-churn), 뉴스 반전 재평가 등 10–15개.
- **향후 시나리오 비용 절감(선택적 v1 포함 판단)**: turn 실행 시 tool 응답을 기록하는 옵션
  (record 모드)을 fixture 팩토리에 함께 설계하면, 이후의 실사건은 자동 박제 가능해진다.

### FR-4: promptfoo Python provider — **orchestrator 경유 필수** (critic 2라운드 HIGH-2)
- turn 실행은 `AgentSession` 직접 호출이 아니라 **`OrchestratorAgent`를 통한다**: constitution
  + F64 guidance + F65 lessons recall은 orchestrator의 `_assemble_turn`이 주입하고
  (`orchestrator.py:148-150,249-326`), `prompt_version` 스탬프도 orchestrator의 `_stamp_new`가
  수행한다. AgentSession만 쓰면 guidance 레이어가 통째로 빠져 **FR-7의 guidance 버전 축이
  프롬프트에 반영되지 않는다** (matrix 컬럼이 전부 동일해짐). `OrchestratorAgent.__init__`은
  session + universe만 필수(broker/executor 무관)라 재사용 비용이 낮음 — 코드로 확인됨.
- (시나리오, guidance 버전, 런)별 **임시 격리 workspace**를 구성하고 orchestrator의
  `journal.root`를 그곳으로 지정한다. 내부 `AgentSession`은 `one_shot=True`
  (날짜-키 세션 resume 사용 금지).
- 산출물 추출: turn 전후 `read_decisions()` 차분(검증된 torn-write-safe 패턴), thesis 파일
  diff, 응답 텍스트 → 구조화 JSON으로 promptfoo에 반환.
- 동시 실행은 구독 rate limit 내로 cap (promptfoo concurrency 설정).

### FR-5: Tier-1 결정적 채점
- **하드(차단 가능) 체크**: decisions.jsonl 스키마 적합성, 산출물 추출 무결성 — 진짜 결정적.
- **non-blocking 행동 체크** (사용자 결정): 트리거 발화 시 기대 (action,side) 집합 내 액션
  존재, 무트리거 시 no-churn, lessons_cited 인용 여부 등 — 리포트로 축적, flake rate 데이터
  확보 후 게이트 승격 재판단. 단 `lessons_cited`는 LLM이 스키마대로 emit해야 하는 필드로
  **현재 라이브 decisions.jsonl에 0건**(관찰됨) — 인용률 자체를 측정 지표로 다루되 합부
  판정에 쓰지 않는다.
- **가드레일 채점은 룰 재구현 금지**: 산출 Decision을 **실제 `DecisionExecutor`**에 통과시켜
  `ExecutionOutcome.status`(skipped_not_shortable 등)로 판정한다. 필요한 의존성 전체
  (critic 2라운드 MEDIUM-2로 명시): 브로커(기존 `SimulatedBroker` 재사용 우선) +
  `RiskManager(use_bracket_orders=True)`(생성자가 검증함, `executor.py:58-61`;
  `evaluate_signal`은 price/portfolio를 인자로 받는 순수 함수) + fixture data_provider +
  universe. 진입점은 **`execute_decision(d)`**(cursor-free) — `execute_pending`은
  market-open 게이트 + `.executor_state.json` 커서 부수효과가 있어 사용 금지.

### FR-6: Tier-2 LLM-as-judge 채점
- turn 타입별 루브릭을 `evals/rubrics/`에 repo 버전 관리. promptfoo `llm-rubric`이
  `ANTHROPIC_API_KEY`로 Claude judge를 사용 (wrapper 불필요).
- 채점 차원: 뉴스 반전 인지·thesis 충돌 명시 여부, linger 여부, 4-factor lens(lesson #13)
  적용, fresh-data 근거 vs 기억 의존.
- **실행은 수동 on-demand** (사용자 결정): 명시적 CLI 실행만(프롬프트/guidance 변경 시).
  nightly 자동화는 운영 데이터 확보 후 별도 결정. F61 Tier-2와 동일한 운영 모델.

### FR-7: Matrix + 리포트
- 1차 축 = **F64 guidance 버전**(`workspace/guidance/history.json`의 버전들) × 시나리오.
  `prompts.py`/`CLAUDE.md` 코드 변경 회귀는 git 브랜치 vs main에서 같은 suite를 돌려 비교
  (축 혼합 금지 — critic HIGH-2).
- promptfoo 웹 뷰어로 버전 간 side-by-side diff 확인.

## 4. 비기능 요구사항 (NFR)

- **NFR-1 (zero-token 기본)**: 기존 `pytest`/CI 기본 실행은 LLM을 절대 호출하지 않는다.
  eval 실행은 명시적 진입점뿐 (F61 원칙 유지).
- **NFR-2 (프로덕션 격리)**: eval은 운영 `workspace/`·실브로커·운영 decisions.jsonl을 절대
  건드리지 않는다. 브로커는 FakeBroker, workspace는 임시 디렉터리. 프로덕션 거래 경로 코드
  변경은 tools 팩토리 리팩터링(동작 보존)뿐.
- **NFR-3 (비결정성 수용)**: LLM 행동의 비결정성을 전제로 한다 — 행동 채점은 non-blocking,
  모든 런은 run-id·타임스탬프로 라벨링, 동일 시나리오 반복 실행 결과를 누적 비교 가능해야 한다.
- **NFR-4 (웹 툴 허용)** (사용자 결정): 피평가 agent는 프로덕션과 동일하게 WebSearch/WebFetch
  사용 가능. 귀결: 시나리오는 실사건 리플레이 우선(가공 사건이 실제 웹과 모순되지 않게),
  루브릭은 웹발 노이즈를 감안해 "행동의 방향"을 채점. 순수 가공 시나리오는 웹과 충돌하지 않는
  소형 사건으로 한정.
- **NFR-5 (비용 구조)**: 피평가 agent = `claude -p`(구독 OAuth), judge = `ANTHROPIC_API_KEY`
  (종량, on-demand 실행만). promptfoo는 `evals/` 하위 고정 버전 의존성(Node)으로 설치하며
  루트 Python 의존성에 영향 없음.
- **NFR-6 (PBT — Partial, PBT-02/03/07/08/09 적용)**: 시나리오 직렬화/역직렬화 round-trip,
  (action,side) 허용 집합 매칭의 불변식, fixture 계약 응답 스키마에 hypothesis 기반 property
  테스트. 도메인 제너레이터(Decision, 시나리오)는 재사용 가능하게 중앙화, seed 로깅/shrinking
  기본 유지, CI 포함(zero-token — 순수 함수만).

## 5. 명시적 Out of Scope (v2 이연)

1. **F64 test-then-adopt 게이트** — `self_rewrite.py:171` 즉시 swap을 candidate 상태 +
   `adopt(gate_fn)`으로 리팩터링해야 가능(critic 확인). 별도 트랙.
2. morning research turn(3-round) 시나리오 — 토큰 비용 큼.
3. red-team(뉴스 헤드라인 prompt injection) 자동 생성 — promptfoo 모듈 활용은 v2.
4. 웹 툴 스텁/fixture 모드.
5. nightly 자동 실행(로컬 cron/GitHub Actions).

## 6. 수용 기준 (요약)

- [ ] fixture 모드에서 13개 tool 명령이 전부 시나리오 JSON으로 응답하고(주입 seam 없던 8개
      명령 포함), 미정의 키는 명시 에러 (실데이터 폴백 없음)
- [ ] 추출기 골격 + 수동 보강으로 만든 실사건 시나리오 ≥ 10개 (wake/intraday/EOD 커버,
      추출기가 자동 슬라이스/TODO 마커를 구분 표기)
- [ ] guidance 버전을 바꿔 같은 시나리오를 돌리면 **프롬프트에 실제로 다른 guidance가 주입됨**
      을 turn 로그로 확인 가능 (orchestrator 경유 증명)
- [ ] `promptfoo eval` 1회 실행으로 전 시나리오에 대해 Tier-1 리포트 생성 (LLM judge 없이)
- [ ] Tier-2 on-demand 실행 시 루브릭 채점 결과가 promptfoo 뷰어에서 시나리오×버전으로 비교 가능
- [ ] 기존 `pytest` 전체 실행이 토큰 0으로 통과 (PBT 포함)
- [ ] 운영 workspace/브로커에 어떤 부수효과도 없음 (격리 테스트로 증명)

## 7. 잔여 미결정 (다음 단계에서)

- promptfoo 버전 고정 방식(bunx vs evals/package.json devDependency) — Application Design
- judge 모델 선택(기본 sonnet 제안) 및 루브릭 초안 — Functional Design
- Units 분할(팩토리 리팩터링 / harness / 시나리오+추출기) — Units Generation
