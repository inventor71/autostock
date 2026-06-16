# F85 — Aggressiveness 노브 요구사항

> Requirements Analysis (standard depth). 조사 → 스코프 UAQ 확정 후 작성.
> 관련 메모리: [[llm-trader-redesign]] · [[risk-execution-redesign]] · [[f60 short master toggle]] · [[f64-f65-self-learning-design]]

## 1. 의도 (Intent)
운영자가 시스템의 **매매 공격성**을 한 개의 다이얼로 조절한다. 공격성은 코드상 두 레이어
(에이전트 프롬프트 성향 + 결정론적 리스크 게이트)에 흩어져 있으므로, **한 다이얼이 두 레이어를
일관되게 동시에 움직여야** 실제 거래 행동에 효과가 난다.

## 2. 확정된 설계 결정 (UAQ, 2026-06-14)
| # | 결정 | 값 |
|---|------|----|
| D1 | 노브 개수/형태 | **단일 합성 다이얼 1개** (프리셋 팬아웃) |
| D2 | 영향 레이어 | **프롬프트 + 리스크 게이트 둘 다** |
| D3 | 값 표현 | **이산 레벨** `conservative \| balanced \| aggressive` |
| D4 | 적용 경로 | **정적 `config/settings.yaml` + 데몬 재시작** (`shorting_enabled` 패턴) |

## 3. 기능 요구사항 (FR)

- **FR-1 (설정 키).** `config/settings.yaml`에 단일 키를 추가한다 — 후보: `agent.aggressiveness`
  (또는 `risk.aggressiveness`; 두 레이어를 가로지르므로 위치는 설계 단계에서 확정).
  허용값 `conservative | balanced | aggressive`. **기본값 = `balanced`**. 누락/오타 시
  **fail-safe로 `balanced`** 로 폴백(거부가 아니라 안전 기본). pydantic Settings에서 검증.

- **FR-2 (레이어 A — 프롬프트 팬아웃).** 레벨에 따라 에이전트 프롬프트의 **성향 블록**이 바뀐다.
  - 주입 지점은 **`src/agent/prompts.py`** (이미 `shorting_enabled`/`signal_brief` 플래그로
    프롬프트를 조립하는 선례). 새 `aggressiveness` 인자를 동일 패턴으로 추가.
  - 와이어링: **`src/agent/orchestrator.py`** 가 `morning_research_prompt(...)` 등에 레벨 전달
    (`_shorting_enabled` 와 같은 자리). **`main.py`** 가 `settings`에서 읽어 orchestrator로 주입.
  - 영향 문구: discovery의 확신 임계("only on genuine conviction"), 진입 의향, synthesis의
    "quality over quantity" 강도, 목표 R:R 권고. (구체 문구는 Functional Design에서 확정.)
  - **CLAUDE.md 운영 매뉴얼**(`src/agent/templates/CLAUDE.md`)의 하드코딩된
    `1. Be conservative — when the setup is unclear, HOLD.` 는 **중립화하고 성향은 per-turn 주입으로
    이전**(durable 템플릿을 레벨마다 갈아끼우는 것보다 안전·검증 용이). — 설계 단계 확정 사항.

- **FR-3 (레이어 B — 리스크 게이트 팬아웃).** 레벨에 따라 `RiskManager`/`PositionSizer`의
  튜너블이 프리셋 묶음으로 바뀐다. 대상 파라미터(현 `risk:` 블록):
  `max_position_pct`, `max_portfolio_risk`, `max_open_positions`, `max_stop_distance_pct`,
  `atr_stop_multiple`, `default_risk_reward`, `take_profit_pct`, `stop_loss_pct`,
  `market_halt_threshold_pct`.
  - 적용 지점: **`main.py:290-305` 및 `main.py:399-414`** 의 `RiskManager(...)` 구성 두 자리.
    레벨 → 파라미터 표를 한 곳(예: `src/risk/` 의 preset 모듈)에서 해석해 두 자리에 동일 적용.

- **FR-4 (단일 진실 소스).** 레벨 → (프롬프트 성향, 리스크 파라미터) 매핑은 **한 곳에 표로** 정의
  (감사·테스트·설명 용이, D3 이산 레벨 채택 이유). 매직 넘버 산재 금지.

- **FR-5 (관찰 가능성).** 데몬 startup 로그 + (가능하면) steering 상태에 **현재 레벨**이 보여야
  한다("지금 어떤 공격성으로 도는가"를 운영자가 확인). 최소한 로그 1줄.

- **FR-6 (안전 상호작용).** Aggressiveness는 **F60 숏 마스터 토글(`shorting_enabled`)을 절대
  오버라이드하지 않는다.** 숏이 꺼져 있으면 `aggressive`라도 숏을 켜지 않는다. 공격성은 숏이 이미
  켜진 경우의 *성향*에만 영향(설계 단계에서 숏 appetite 포함 여부 결정).

## 4. 레벨 → 파라미터 매핑 (지시적 초안 — 최종 캘리브레이션은 Functional Design)
> `balanced` ≈ 현행 shipped 값 기준. conservative=타이트, aggressive=루즈. 숫자는 설계 단계 확정.

| 파라미터 | conservative | balanced (현행) | aggressive |
|---|---|---|---|
| `max_position_pct` | 0.03 | 0.05 | 0.08 |
| `max_portfolio_risk` | 0.01 | 0.02 | 0.03 |
| `max_open_positions` | 8 | 20 | 25 |
| `max_stop_distance_pct` | 0.08 | 0.12 | 0.15 |
| `default_risk_reward` | 3.0 | 2.5 | 1.8 |
| 프롬프트 성향 | "불확실하면 HOLD, 고확신만" | 현행 | "실행가능 셋업에 적극 진입, 후보 다수 허용" |

## 5. 비기능 요구사항 (NFR)
- **NFR-1 (하위호환).** 키 누락 시 동작이 **현행(balanced)과 동일** — 기존 배포 영향 0.
- **NFR-2 (안전 기본).** 잘못된 값 → 거부/크래시 아닌 `balanced` 폴백 + 경고 로그(fail-safe).
- **NFR-3 (테스트 용이성).** 매핑은 순수 함수/데이터 → 단위 테스트로 각 레벨 파라미터 검증.
- **NFR-4 (자가학습 정합).** [[f64-f65-self-learning-design]] 의 불변 헌장(CONSTITUTION)과 충돌
  없어야 함. 노브는 헌장 경계 *안*에서 성향만 조절(헌장 자체는 불변).

## 6. 범위 외 (Out of scope, 후속 후보)
- 런타임 steering 명령으로 즉시 변경 (D4에서 정적 config 우선 선택; 후속 스택 가능).
- 숫자 연속 스케일(0–1) + 보간 (D3에서 이산 레벨 선택).
- 자가학습(F64)이 레벨을 자동 조정 (헌장/안전 검토 필요한 별도 에픽).
- `multi_agent.n_agents` / reflection 깊이 연동 (공격성보다 '철저함' 축 — 분리).

## 7. 추가 검토 필요 / Open
- 설정 키 위치: `agent.aggressiveness` vs `risk.aggressiveness` vs 최상위 (설계 단계 확정).
- `aggressive`가 숏 appetite를 건드릴지(FR-6 단서) — 기본은 No, 설계 시 재확인.

## 8. 단타/장투 철학 모사 — 프레임워크 레버 + critical 보강 (2026-06-14 사용자 심화)
> 사용자 의도: aggressive = **단타(day-trade/모멘텀)** 를 시도하고 **기존 프레임워크로 학습**까지
> 가능해야 함. conservative = **장투(저평가 가치)** 위주 발굴 + **더 긴 주기 레슨**. 즉 aggressiveness는
> 리스크 숫자가 아니라 **"학습 루프의 시간축(horizon)"** 을 바꾸는 다이얼.

### 8.1 조사 — 시간축이 고정되어 있는 지점
> ⚠️ **Critic 정정 (2026-06-14):** 아래 `horizon=5`는 **사람용 EOD 품질요약**(metrics.py)에만 적용되며
> **학습(efficacy) 경로와 무관**하다. 학습이 쓰는 `excess`는 `collector._attach_excess`가 **전체
> price_path**에 걸쳐 계산 — 청산 round-trip은 실보유기간, **미청산은 `lookback_days=30`**
> (`collector.py:336-344`). `efficacy.lesson_efficacy`/`prompt_version_efficacy`(`efficacy.py:66-102`)는
> `o.excess`를 **horizon/level 필터 전혀 없이** 버킷팅한다. 따라서 §9를 볼 것 — C3는 "파라미터 확대"가
> 아니라 efficacy를 결정별 horizon으로 bound + 미성숙 제외하는 **신규 게이팅**이다.
- (사람용 요약) horizon = **5일 고정**: `quality/metrics.py` `direction_hit_rate`/`confidence_calibration`/
  `exit_timing(horizon=5)`, `stop_quality(post_trigger_days=5)`.
- outcome 수집 = **일봉**(`collector._fetch_daily_ohlc`) + `collect_outcomes(lookback_days=30)`.
- 레슨 recall 시간성: `recall.RecallWeights(recency=0.5)`, `_recency=1/(1+age)`,
  `mark_retirements(idle_days=180)` — 전부 인자화돼 있으나 호출부에서 고정.
- intraday 턴 = **"do not churn"** 고정(`prompts.intraday_prompt`).
- ✅ **결정 스탬핑 메커니즘 이미 존재**: `orchestrator.py:268-276` 가 `Decision.prompt_version`(F62)을
  사후 스탬핑 → 같은 자리에 `aggressiveness`/horizon 스탬핑 가능.

### 8.2 레벨 → 레버 매핑 (차원 확장)
| 차원 | conservative(장투) | balanced | aggressive(단타) | 레버 위치 |
|---|---|---|---|---|
| 발굴 포커스 | 저평가·펀더멘털·insider·institutional·평균회귀 | 혼합 | movers·모멘텀·브레이크아웃·거래량·catalyst | `prompts.py` discovery+signal guide |
| 보유 horizon/`valid_until` | 길게(주~월) | 중간 | 짧게(당일~수일) | 프롬프트 + `Decision.valid_until` |
| intraday 턴 행동 | 대부분 HOLD | 트리거 시 | 적극 진입·청산 | `intraday_prompt` + scheduler 간격 |
| 리스크 게이트 | 작은 사이즈·적은 포지션 | 현행 | 큰 회전·타이트 스톱 | `RiskManager`/`settings.yaml risk:` |
| 채점 horizon | 길게(20~60d)·벤치마크 초과 | 5d | 짧게(1~2d)·intraday | `metrics.py`/`collector.py` |
| 레슨 시간성 | recency↓·idle 길게 | 현행 | recency↑·idle 짧게 | `recall.py` |
| EOD 레슨 종류 | 가치/촉매 성숙/인내 | 혼합 | 진입타이밍/청산규율/모멘텀 소멸 | `eod_review_prompt` |

### 8.3 Critical 보강 (트랙 검토 대상)
- **C1 [공통·아키텍처] 결정에 horizon/level 스탬핑** ⭐ — F62 스탬핑 재사용. 채점이 "그 결정이
  만들어진 시간축"으로 평가되게(글로벌 현재 레벨 아님). 없으면 레벨 변경 시 in-flight 결정 채점 오염.
  저비용·고정합성 → **포함 강력 권장.**
- **C2 [aggressive 필수] 단기/intraday 채점** — 5일 일봉으론 단타 학습 불가. IntradayFeatureStore
  (F80/F82, 이미 적재 중)로 price_path 공급. 최소안=horizon 1~2일+일봉 / 완전안=intraday price_path.
  [[f80-storage-format-rationale]]
- **C3 [conservative 필수] 장기 윈도우 + 미성숙 결정 보류** — `lookback_days`/`horizon` 레벨 파생 확대 +
  horizon 미도달 결정 채점 보류(efficacy 왜곡 방지) + 장기 미청산 mark-to-benchmark.
- **C4 [둘 다] 레슨 시간성 파라미터화** — `recall` recency 가중·`idle_days` 레벨 파생. 함수는 이미
  인자 수용 → 배선만.

### 8.4 스코프 확정 (UAQ, 2026-06-14)
**F85 포함:**
- **A** — 프롬프트 발굴 포커스 + 리스크 게이트 프리셋 (레벨별). 리스크 preset은 §9.1 overlay-only.
- **C1** — `Decision`에 horizon/level 스탬핑 (F62 `prompt_version` 스탬핑 메커니즘 재사용).
- **C3-full (일봉)** — `metrics.py`/`collector.py`의 horizon·`lookback_days`를 레벨 파생으로
  (aggressive=짧게 1~2d, conservative=길게 20~60d, 채점은 일봉 유지) **+ maturity 게이트**
  (`today−decision.ts < horizon` → efficacy 제외) **+ 성숙 시점 1회 확정채점 grading-state 영속**.
  F74와 무관(별개 시스템), 기존 quality 파이프라인 내부 신규 로직. → §9.2 Q1 확정.
- **C4 (recency만)** — `recall_lessons`에 `weights=RecallWeights(recency=level파생)` 주입
  (`orchestrator.py:321`). **idle_days 은퇴는 후속** (호출부·영속화 신규라 제외). → §9.2 Q2 확정.
- **intraday churn 문구 레벨화** — `intraday_prompt` 만; scheduler 틱 간격은 불변(데몬 안정).
- **F74 레벨 행동 검증 (재사용)** — `evals/`에 conservative/aggressive 시나리오 + `guidance_label`
  행 추가(`tests.yaml`). 새 채점기 금지. → §10 / §9.2 Q2(F74) 확정. **F74 nightly 자동화 연결은 제외.**

**F85 제외 → 후속 스택 트랙:**
- **C2-full** — IntradayFeatureStore(F80/F82) intraday price_path로 단타 채점(매칭/round-trip 신규
  파이프라인). C1 스탬핑이 깔려 있으면 후속에서 horizon 소스만 intraday로 교체하면 됨.
- scheduler 틱 간격 레벨화.

## 9. Critic 적대 검토 반영 (격리 서브에이전트, 2026-06-14, 전부 코드로 교차검증)
> 문서의 "이미 존재/배선만/즉시" 단정을 실제 코드로 검증. 엔지니어링 보강은 FR에 직접 반영(아래),
> 스코프 영향 2건은 §9.2에서 사용자 결정 대기.

### 9.1 엔지니어링 보강 (확정 반영)
- **FR-1 보강 (fail-safe 신규).** `config/config.py`에 `field_validator` 전무, 선례 `mode: Literal`
  (`config.py:115`)은 오타 시 **크래시**. ⇒ 새 키에 `field_validator(mode="before")`로 비멤버→`balanced`
  매핑 + 경고 로그 + 오타-경로 단위테스트. (NFR-2 충족의 실제 구현 비용.)
- **FR-2 보강 (전수 배선).** 결정-생성 프롬프트 빌더를 **전부 열거**해 레벨 주입: `morning_research_prompt`,
  `multi_research_initial_prompt`, `synthesis_prompt`, `sub_agent_prompt`, `parallel_synthesis_prompt`,
  `intraday_prompt`(churn 문구), `eod_review_prompt`, `wake_prompt`. `shorting_enabled` 선례는 2개만
  배선된 **부분 패턴** — 그대로 베끼면 synthesis/intraday가 `balanced`로 조용히 폴백.
- **FR-3/FR-6 보강 (overlay-only).** preset은 §3 FR-3의 **named 필드 allowlist를 현 settings에 머지하는
  overlay**로 구현, `RiskConfig` 통째 교체 금지. `shorting_enabled`가 세 레벨 모두에서 불변임을 단언하는
  테스트 추가(`main.py:300,409` 독립 주입 확인).
- **C1 caveat.** `restamp_decisions`는 손상 라인이 하나라도 있으면 **배치 전체 기록 거부**
  (`journal.py:195-200`) → 그 배치 결정은 default horizon으로 남아 잘못 채점. Functional Design에 명시.

### 9.2 스코프 영향 — 사용자 결정 대기 (UAQ 진행)
- **[HIGH] C3 실제 비용.** "horizon 파라미터 확대"가 아님. 장투 학습이 *작동*하려면 (a) 결정별 horizon
  stamp[C1], (b) **미성숙 결정 채점 제외 게이트**(today−ts ≥ horizon), (c) **성숙 시점 1회 제대로 채점하는
  영속 상태**가 필요. (b)/(c)가 없으면 신선한 장기 결정이 매일 미성숙 채점되어 efficacy 오염 +
  **F64 자동 롤백 오발**(`orchestrator.py:682`). 현재 채점은 `date.today()` 캐시 1회성
  (`orchestrator.py:286-298`)이라 (c)는 **신규 빌드**. → 질문 Q1.
- **[MEDIUM] C4 idle_days.** `mark_retirements`는 **호출부가 src에 없음**(`recall.py:188` 정의만,
  docstring이 영속화를 follow-up이라 명시). recency 가중은 진짜 배선(`orchestrator.py:321`에 `weights=`
  추가)이지만 idle_days 레벨화는 새 EOD 호출부+은퇴 영속화. → 질문 Q2.
  - **확정 (UAQ 2026-06-14): recency 가중치만 레벨화** (`orchestrator.py:321` `weights=` 주입). idle_days
    은퇴 영속화는 후속.
- **[HIGH] C3 확정 (UAQ 2026-06-14): C3-full 포함** — maturity 게이트 + 성숙 시점 1회 확정채점 영속까지
  F85에. F74와 중복 없음(§10). 장투 학습 작동의 필수 조건.

## 10. 기존 채점 자산 재사용 (사용자 지시 — "막 만들면 겹치니 확인하고 넣자", 2026-06-14)
> 사용자: 이미 머지됐지만 자동화 미연결인 "프롬프트 채점" 트랙이 있으니 중복 빌드 금지. 조사 결과
> 그 트랙 = **F74 (Prompt Eval & Regression, promptfoo)**.

**두 채점 시스템은 별개 — 겹치지 않음:**
- **F74 `src/evals/`+`evals/`** = 합성 시나리오 **행동 채점**(promptfoo Tier1/2, 루브릭,
  `guidance_file`/`guidance_label`로 프롬프트 변형 비교). 머지됨, **CI 미배선**(nightly·F64 자동게이트는
  F74 out-of-scope). → aggressiveness **레벨별 행동이 의도대로인지 검증**하는 올바른 기존 도구.
- **F62 `src/agent/quality/`+`efficacy.py`+`self_rewrite.py`** = 라이브 **실결정 결과 채점**. C3 maturity
  게이트가 여기 속함. `quality/`·`learning/`에 maturity 개념 전무(확인) → 신규지만 **기존 파이프라인 내부
  작은 로직**(새 프레임워크 아님), F74와 **중복 없음**.

**F85 재사용 방침:**
- C3 라이브 maturity 게이트 → `quality/collector.py`+`efficacy.py` 내부 신규(중복 아님).
- 레벨 행동 검증 → **F74 eval 재사용**: 레벨별 시나리오 + `guidance_label` 행 추가(새 채점기 금지).
- (선택) F74 nightly/CI 자동화 연결 = 레벨 회귀 게이트 — **확정: F85 제외**(UAQ 2026-06-14, 후속).
  F85는 `evals/tests.yaml`에 레벨별 시나리오 + `guidance_label` 행만 추가.
