# F85 — Functional Design (Aggressiveness 노브)

> 단일 응집 단위. 요구사항 `inception/requirements.md` §1-10 기준. critic 보강 반영.

## 0. 컴포넌트 경계 (Application Design 요약)
```
config.AggressivenessLevel (Literal enum + fail-safe validator)
        │ 읽힘
        ▼
src/agent/aggressiveness.py   ← NEW: SSOT preset 모듈 (순수)
  • AggressivenessProfile (frozen dataclass)
  • PROFILES: dict[level -> Profile]
  • resolve(level) -> Profile        (fail-safe: 비멤버→balanced)
        │ 팬아웃 (main.py가 주입)
        ├─▶ 리스크 레이어: RiskManager(**profile.risk_overlay 머지)
        ├─▶ 프롬프트 레이어: prompts.* (profile.disposition, profile.churn)
        ├─▶ 스탬핑: orchestrator → Decision(grading_horizon_days, aggressiveness)
        └─▶ 학습 레이어: recall(weights=profile.recall_weights),
                          collect_outcomes(maturity 게이트)
```
**SSOT 원칙(FR-4):** 레벨별 숫자/문구는 `aggressiveness.py` PROFILES 한 곳에만. 다른 모듈은 profile을
주입받아 쓰기만 한다. 매직넘버 산재 금지.

## 1. 설정 계층
### 1.1 `config/config.py`
```python
AggressivenessLevel = Literal["conservative", "balanced", "aggressive"]

class AgentConfig(BaseModel):
    ...
    aggressiveness: AggressivenessLevel = "balanced"

    @field_validator("aggressiveness", mode="before")
    @classmethod
    def _coerce_aggr(cls, v):
        # critic: Literal는 비멤버에 ValidationError(크래시) → fail-safe로 흡수
        if isinstance(v, str) and v.lower() in ("conservative", "balanced", "aggressive"):
            return v.lower()
        logger.warning(f"unknown aggressiveness {v!r}; falling back to 'balanced'")
        return "balanced"
```
- 키 위치 = `agent.aggressiveness` (Open §7 해소: agent 턴 행동·학습을 가로지르므로 agent 블록.
  risk overlay는 main.py가 profile에서 끌어 RiskManager에 주입 — 키 자체는 agent에 둠).
- `config/settings.yaml` `agent:` 블록에 `aggressiveness: balanced  # conservative|balanced|aggressive` 추가.

## 2. SSOT preset 모듈 — `src/agent/aggressiveness.py` (NEW, 순수)
```python
@dataclass(frozen=True)
class AggressivenessProfile:
    level: str
    # ── 리스크 overlay (named-field allowlist; critic: 통째 swap 금지) ──
    risk_overlay: dict[str, float]   # 아래 §2.1 키만 허용
    # ── 프롬프트 성향 ──
    disposition: str                 # 발굴/확신/진입 성향 블록 (프롬프트에 주입)
    intraday_churn: str              # intraday_prompt churn 문구
    short_tilt: str                  # 숏 appetite 문구(빈문자열 가능; FR-6: 마스터 토글 불간섭)
    # ── 학습 시간축 ──
    grading_horizon_days: int        # C1 스탬핑 + C3 maturity 기준
    recall_recency: float            # C4 RecallWeights.recency

ALLOWED_RISK_KEYS = {  # critic FR-3: overlay는 이 키만 — shorting_enabled 등 안전게이트 제외
    "max_position_pct", "max_portfolio_risk", "max_open_positions",
    "max_stop_distance_pct", "atr_stop_multiple", "default_risk_reward",
    "take_profit_pct", "stop_loss_pct", "market_halt_threshold_pct",
}

def resolve(level: str | None) -> AggressivenessProfile:
    return PROFILES.get((level or "").lower(), PROFILES["balanced"])  # fail-safe
```

### 2.1 캘리브레이션 표 (balanced = 현행 settings.yaml 값, critic 확인)
| 키 | conservative | balanced(현행) | aggressive |
|----|-------------|----------------|------------|
| max_position_pct | 0.03 | 0.05 | 0.08 |
| max_portfolio_risk | 0.01 | 0.02 | 0.03 |
| max_open_positions | 8 | 20 | 25 |
| max_stop_distance_pct | 0.08 | 0.12 | 0.15 |
| atr_stop_multiple | 3.5 | 3.0 | 2.0 |
| default_risk_reward | 3.0 | 2.5 | 1.8 |
| take_profit_pct | 0.25 | 0.15 | 0.08 |
| stop_loss_pct | 0.07 | 0.05 | 0.04 |
| market_halt_threshold_pct | -0.02 | -0.03 | -0.05 |
| **grading_horizon_days** | **45** | **20** | **3** |
| **recall_recency** | **0.25** | **0.5** | **1.0** |

> 철학: aggressive=타이트 스톱·작은 R:R·빠른 익절·많은 회전(단타) + 짧은 채점/빠른 recency.
> conservative=넓은 스톱·큰 R:R·인내(장투) + 긴 채점/평탄 recency. **balanced는 현행과 100% 동일**
> (NFR-1 하위호환: 키 미설정 시 balanced이므로 기존 배포 동작 불변).
> 숫자는 1차 캘리브레이션 — 운영 데이터로 후속 조정 가능(SSOT라 한 곳 수정).
> **[critic 3차] 경로 분리 주의**: 에이전트 경로(`use_bracket_orders=True`)에선 `stop_loss_pct`/
> `take_profit_pct`가 **진입 사이징·타깃에 안 쓰임** — bracket은 LLM 레벨 또는 `atr_stop_multiple`/
> `default_risk_reward`를 씀(`manager.py:255-276,310`). `stop_loss_pct`/`take_profit_pct`는 **폴링 백업**
> (`check_stop_loss`/`check_take_profit` `manager.py:983,1033`)·`_simple_buy` 폴백에서만 발동. 따라서
> aggressive의 "0.08 익절 vs default_risk_reward 1.8"은 **모순 아님(서로 다른 경로)** — 단 둘 다 살아있어
> bracket 타깃(1.8R)과 폴링 익절(8%)이 먼저 닿는 쪽이 발동. `atr_stop_multiple=2.0`×ATR은
> `max_stop_distance_pct=0.15` 이하라 클램프/거부 없음(자기정합). §2.1은 이 경로 분리를 명시.

### 2.2 프롬프트 성향 블록 (레벨별)
- **conservative.disposition**: "저평가·견고한 펀더멘털 중심으로 발굴하라(낮은 P/E, 평균회귀,
  insider/institutional 매집). 확신이 높을 때만 진입하고 불확실하면 HOLD. 장기 보유를 전제로 넓은 스톱과
  높은 R:R(≥1:3)을 설정하라. `valid_until`을 길게(주~월) 잡아라."
- **balanced.disposition**: **빈 문자열**(§2.3) — CLAUDE.md를 그대로 두므로 현행 프롬프트와 바이트 동일.
- **aggressive.disposition**: "모멘텀·브레이크아웃·거래량 급증·당일 catalyst 중심으로 발굴하라(movers,
  intraday). 적당히 확인된 셋업이면 적극 진입하고 회전을 두려워 말라. 타이트한 스톱과 빠른 익절(R:R≥1:1.5),
  짧은 `valid_until`(당일~수일)을 전제로 단기 우위를 노려라."
- **intraday_churn**: conservative="웬만하면 HOLD — 모닝 계획이 깨지지 않는 한 관망" / aggressive=
  "intraday 트리거(돌파·반전·거래량)에 적극 진입·청산하라" / balanced=현행 "do not churn".
- **short_tilt** (shorting_enabled=True일 때만 의미): aggressive에서만 비어있지 않게 — 단 **FR-6**: 이
  문구는 마스터 토글을 켜지 않으며, 토글 OFF면 프롬프트에 숏 가이던스 자체가 주입 안 됨(현행 게이트 유지).

### 2.3 CLAUDE.md 처리 — **중립화 안 함, delta 주입** (critic 2차 수정 / §11-F)
> ⚠️ 초기안(템플릿 중립화)은 **하위호환 함정**: `journal.init`은 CLAUDE.md를 `if not exists`로만 씀
> (`journal.py:123`) → 기존 워크스페이스는 **옛 CLAUDE.md(보수 문구 포함)를 그대로 유지**한 채 새 주입까지
> 받아 "balanced=현행 동일"이 깨지고 워크스페이스 마이그레이션이 필요해짐.
- **수정안:** `src/agent/templates/CLAUDE.md`는 **건드리지 않는다**(= balanced 기준선). 레벨 성향은 **delta로만**
  주입: **balanced.disposition = 빈 문자열**(현행 프롬프트와 **바이트 동일** → NFR-1 진짜 충족, 마이그레이션
  불필요). conservative/aggressive만 명시적 override tilt를 per-turn 주입(durable 보수문구 위에 최근·상위
  가중으로 얹힘 — LLM이 해소). 기존/신규 워크스페이스 모두 동일하게 작동.

## 3. 프롬프트 팬아웃 (FR-2, critic 전수 배선)
`disposition`/`churn`/`short_tilt`을 받는 인자를 **모든 결정-생성 빌더**에 추가:
`morning_research_prompt`, `multi_research_initial_prompt`, `synthesis_prompt`, `sub_agent_prompt`,
`parallel_synthesis_prompt`, `intraday_prompt`, `wake_prompt`.
- **[critic LOW]** `debate_prompt`(`prompts.py:315`)는 결정-비생성(이전 견해 challenge 라운드)이라 **제외**(정상).
  `eod_review_prompt`는 채점/리뷰 턴이라 disposition 주입 **불필요** → 제외(요약 framing은 §6.2 pending 표기로).
- `orchestrator.py`: `_aggr_profile` 필드 보관(생성자 인자), 각 빌더 호출부(`:227,361,390,487,536,565,
  637,648,657`)에 주입.
- `main.py:427`: `AgentTradingLoop(..., aggressiveness=settings.agent.aggressiveness)` (orchestrator가
  내부에서 `resolve()` 호출). 인자 누락 빌더가 없도록 단위테스트로 전수 확인.

## 4. Decision 스탬핑 (C1)
`journal.py` Decision에 2필드 추가(legacy 라인은 default로 파싱 — `prompt_version` 선례 동일):
```python
aggressiveness: str = "balanced"      # 결정 생성 시점 레벨 (행동 귀속)
grading_horizon_days: int = 20        # 결정 생성 시점 horizon (C3 maturity 기준)
```
- 스탬핑: `orchestrator._stamp_new`(`:266-278`)에서 `prompt_version`과 같은 자리에 두 필드 세팅 후
  `restamp_decisions` 재기록.
- **critic caveat**: `restamp_decisions`는 손상 라인 있으면 배치 전체 기록 거부(`journal.py:195-200`)
  → 그 배치 결정은 default(20/balanced)로 채점됨. functional 한계로 명시, 로그 경고 추가.
- **[critic MEDIUM] human 결정은 스탬핑 경로 밖**: 스티어링 결정(`commands.py:434-506`)은 `_stamp_new`를
  안 거침. §6.2대로 grading에서 `source=="human"` 제외하므로 misgrade 무해(스탬프 자체는 default로 남아도 됨).

## 5. 리스크 overlay (FR-3, critic overlay-only) — critic MEDIUM(use_bracket_orders) 반영
- **단일 chokepoint로 통합**: 리스크 구성이 두 곳에 흩어져 있음 — 헬퍼 `_build_risk_manager(settings, *,
  use_bracket_orders)`(`main.py:484-506`, batch 경로 `use_bracket_orders=False`)와 **에이전트 경로 인라인**
  RiskManager(`use_bracket_orders=True`, `main.py:413`). overlay를 **`_build_risk_manager` 안에서만** 적용하고
  에이전트 경로도 이 헬퍼를 쓰도록 합류시킨다(중복 제거).
```python
def _build_risk_manager(settings, *, use_bracket_orders):
    profile = resolve(settings.agent.aggressiveness)
    risk_kwargs = {**settings.risk.model_dump(), **profile.risk_overlay}  # named overlay
    # shorting_enabled/short_*/individual_stock_halt_pct 는 RiskConfig 필드라 model_dump()에 포함됨
    # → overlay 키(ALLOWED_RISK_KEYS)에 없으므로 settings 값 그대로 통과(FR-6).
    return RiskManager(use_bracket_orders=use_bracket_orders, **selected(risk_kwargs))
```
- **[critic MEDIUM]** `use_bracket_orders`는 settings 필드가 아니라 **per-site 명시 인자** — overlay/allowlist에
  넣지 말 것(넣으면 에이전트 경로에서 `True`가 누락돼 bracket/OCO 보호가 조용히 꺼짐 = 안전 회귀).
- 테스트: (a) 세 레벨 모두 `risk_manager.shorting_enabled == settings.risk.shorting_enabled`,
  (b) **에이전트 경로 `risk_manager.use_bracket_orders is True`**, (c) overlay가 short_* 파라미터 불변.

## 6. 학습 — C3 maturity 게이트 + grade 영속, C4 recency
### 6.1 maturity 게이트 (`quality/collector.py`) — critic HIGH-1 반영
- 각 결정의 성숙도: `mature = round_trip_closed OR (today - decision.ts.date()).days >= decision.grading_horizon_days`.
- **미성숙 & 미청산** 결정 → efficacy 버킷에서 제외(EOD 요약엔 "pending"으로 노출).
- OPEN 결정 price_path 윈도우를 `[ts, ts + grading_horizon_days]`로 슬라이스(현 flat `lookback_days=30` 대체).
- **[critic HIGH-1] OHLC fetch 윈도우도 horizon에 맞춰야 함.** 현 `collect_outcomes`는
  `end=latest + timedelta(days=lookback_days=30)` 고정(`collector.py:303`)이라 conservative horizon=45는
  fetch 윈도우(30)를 **초과** → 슬라이스가 +30에서 잘려 성숙해도 데이터 부족(`benchmark_excess`는 len≥2
  필요, `metrics.py:145`)으로 영구 제외됨. **수정**: `end = max(latest + max(lookback_days,
  max(d.grading_horizon_days for d in buy_sell)), max(rt.closed_at for closed RTs), today)`.
  (critic 3차: `latest`는 결정 ts 기준이라 **늦게 청산된 round-trip의 `closed_at`이 그걸 초과**할 수 있음 —
  exit는 decision ts와 독립이므로 `closed_at`·`today`도 상한에 포함.) 테스트: 최장 horizon 결정 +
  최근 청산 RT 모두 `ts+horizon`/`closed_at`까지 캐시 span 단언.

### 6.2 grade 영속 (성숙 시점 1회 확정) — `workspace/grades.jsonl` (NEW) — critic HIGH-2 반영
- **키 = decision 라인 인덱스**(`decision_index`, execution 매칭에 이미 쓰는 안정 식별자 `collector.py:132`).
  critic: `(ts,symbol,action)`는 LLM이 직접 쓰는 `ts`(`CLAUDE.md:71` 스키마) 충돌 가능 — 라인 인덱스가 안전.
- **[critic 3차] 불변식 명시 + ts 교차검증**: `decision_index`는 `read_decisions()`의 **파싱 성공 결정**
  enumerate 인덱스(`collector.py:285`)라, decisions.jsonl이 **append-only·무삭제·무재정렬**일 때만 안정.
  cheap 보험: grade 레코드에 결정 `ts`도 저장하고 재읽기 시 인덱스→ts 불일치면 **fail-safe skip**(가지치기/복구
  같은 미래 op가 인덱스를 밀어도 오귀속 방지). `restamp_decisions`는 순서·개수 보존(손상 시 배치 거부 `journal.py:195`).
- 레코드: `{decision_index, ts, graded_at, level, horizon_days, excess, win, window:[from,to]}`.
- 흐름: `grade_matured(journal)` — grades.jsonl을 **append 직전 재읽기**해 이미 있는 `decision_index`는 skip,
  mature인 결정만 `[ts, ts+horizon]` excess 1회 append. 성숙 후 가격 드리프트로 점수 안 흔들림 + 감사 추적.
- **[critic HIGH-2] writer 불변식 명시**: `grade_matured`는 **데몬 EOD 경로에서만** 호출한다. `collect_outcomes`
  **내부에 두지 않는다** — read-only 리포트 CLI(`quality/__main__.py:29`)가 그걸 호출하므로, 안에 두면 CLI가
  2번째 writer가 됨. append-only(JSONL torn-safe) [[f80-storage-format-rationale]]. EOD 1턴 내 중복 호출
  방지 위해 append 직전 파일 재읽기로 dedup(인메모리 stale view 금지).
- **[critic MEDIUM] `source="human"` 결정 제외**: 스티어링 콘솔 결정(`commands.py:434-506`,
  `Decision(source="human")`)은 `orchestrator._stamp_new`를 안 거쳐 default(20/balanced)로 남음 → 에이전트
  행동이 아니므로 **grading/efficacy에서 통째 제외**(귀속 오염 방지). collect_outcomes에서 `source=="human"` 필터.
- `efficacy.lesson_efficacy`/`prompt_version_efficacy` 입력 = (영속 grade ∪ 청산 round-trip) − 미성숙 − human.
  → F64 자동롤백이 미성숙/사람 노이즈로 오발하지 않음.
- **[critic HIGH-2 / UAQ] excess per-day 정규화.** efficacy 버킷에 넣기 전 `excess_norm = excess /
  max(holding_days, 1)`(holding_days = grade window 일수 또는 round-trip 보유일)로 정규화 → 2일·45일
  excess가 per-day 기준 비교가능. `win_rate`(부호)는 양수 제수라 불변, `avg_excess` 크기만 정규화 →
  `maybe_rollback` 평균 비교가 사과↔사과. (기존 F62 선재 한계도 동반 개선. F62 efficacy 의미가 'per-day
  excess'로 바뀜을 release note에 명시.) `efficacy.py` `lesson_efficacy`/`prompt_version_efficacy`의
  `o.excess` append 지점에 정규화 적용; raw `excess`는 grade 레코드·EOD 요약에 보존.
- **[critic HIGH-1 / UAQ] aggressive=단기 스윙(horizon 3d), 같은날 스캘프 학습은 C2 후속.** 같은 날 청산
  round-trip은 일봉 1 bar라 ungradeable(`_to_naive_ts` 자정정규화) — aggressive는 *거래*는 단타로 하되
  **학습 신호는 1~3일 스윙**에서 확보. 순수 같은날 스캘프의 학습은 **C2-full(intraday price_path) 후속**.
  FD가 이를 정직히 스코프(과장 금지). EOD 요약에 같은날 미채점 건수 노출.
- **[critic MEDIUM] conservative 콜드스타트 알려진 한계**: horizon=45면 첫 ~45일간 거의 모든 결정이 미성숙 →
  efficacy/EOD 품질요약이 비다시피 함(크래시 아님; `maybe_rollback`은 None/n_days에 안전 no-op
  `self_rewrite.py:193,197`, `should_rewrite`는 `MIN_EFFICACY_SAMPLE=20` 게이트로 no-op). 완화: (a) 청산
  round-trip은 어려도 즉시 성숙 처리, (b) EOD 요약에 "N pending / M graded" 표기해 운영자가 '고장'으로 오해 안 하게.

### 6.3 C4 recency (`orchestrator.py:321`)
```python
return recall_lessons(all_lessons, fp, self._lesson_efficacy(),
                      k=self._reflection_max_lessons,
                      weights=RecallWeights(recency=profile.recall_recency))
```
- idle_days 은퇴는 후속(호출부·영속화 신규 — 본 트랙 제외).

## 7. F74 레벨 행동 검증 (재사용, 새 채점기 금지)
`evals/tests.yaml`에 행 추가:
- 시나리오 `aggressive-momentum-daytrade`(급등/돌파 fixture → 적극 진입·타이트스톱 기대),
  `conservative-value-hold`(저평가/횡보 fixture → 관망/HOLD·넓은스톱 기대).
- `guidance_label: aggressiveness=<level>`로 레벨 변형 비교(F74 기존 메커니즘).
- 새 루브릭/채점기 추가하지 않음 — 기존 behavior_grade 재사용.

## 8. 관찰성 (FR-5)
- 데몬 startup 로그 1줄: `Aggressiveness: {level} (horizon={d}d, max_pos={pct})`.
- (선택, 후속) steering health/status에 현재 레벨 노출.

## 9. NFR (경량)
- **NFR-1**: balanced=현행 동일, 키 미설정→balanced → 기존 배포 영향 0 (테스트로 증명).
- **NFR-2**: 오타→balanced(§1.1 validator), 크래시 없음.
- **NFR-3**: PROFILES/resolve/maturity 전부 순수 → property-based 테스트(단조성·경계).
- **NFR-4**: F64 헌장 불변 — 노브는 성향만, 헌장 경계 안.

## 10. 테스트 계획
- **unit**: validator fail-safe(오타→balanced), resolve(3레벨+unknown), overlay가 shorting_enabled 불변,
  Decision 2필드 round-trip(legacy 파싱), 빌더 전수 인자 수용, maturity 게이트(경계: =horizon),
  grade 영속 멱등(2회 호출=1 레코드).
- **example-based(3 프로필 고정)**: 레벨 정렬 시 max_position_pct↑·grading_horizon_days↓ 단조성
  (critic 3차: PROFILES는 3-엔트리 dict라 이건 생성형 PBT가 아니라 3개 하드코딩 assert — 정직히 표기).
- **property (hypothesis, 진짜 생성형)**: `resolve(arbitrary_str)`=balanced(3멤버 외 전부) fail-safe;
  maturity 경계 `(today−ts).days >= horizon`을 생성된 `(ts, horizon, today)` 쌍 위에서.
- **integration**: 세 레벨로 morning turn 조립 시 프롬프트에 올바른 disposition 포함; main.py 와이어링
  스모크(데몬 startup, balanced=현행).
- **F74**: 레벨 시나리오 스모크(구독 토큰, maxConcurrency=1).
- **[critic 2차 추가]** fetch 윈도우 ≥ 최장 horizon span; grade 멱등(2회=1, decision_index dedup);
  human 결정 grading 제외; agent 경로 `use_bracket_orders is True`; 기존(비-fresh) 워크스페이스에서
  balanced 프롬프트 = 현행 동일.

## 11. Critic 2차 적대 검토 반영 (2026-06-16, 전부 코드 교차검증)
> FD가 구체 코드 접점을 명시하자 critic이 6건 적출. 전부 엔지니어링 보강(정책 분기 없음) — 직접 반영.

- **[HIGH-1] fetch 윈도우 ≠ horizon** (`collector.py:303` `end=latest+30` 고정 vs slice `[ts, ts+horizon]`).
  conservative(45)·심지어 balanced(20)도 데이터 잘림 → 성숙해도 영구 제외. **수정 §6.1**: fetch end를
  `max(lookback_days, max horizon)`로.
- **[HIGH-2] grades.jsonl 키·writer 가정** — `(ts,symbol,action)`는 LLM-작성 ts 충돌 가능 → **decision_index
  키**로. `collect_outcomes`를 read-only CLI(`__main__.py:29`)가 호출하므로 grade-write는 **데몬 EOD 경로
  전용**(collect_outcomes 내부 금지). append 직전 재읽기 dedup. **수정 §6.2**.
- **[MED] human 결정 우회** (`commands.py:434-506` `source="human"`은 `_stamp_new` 미경유) → grading에서
  `source=="human"` **제외**. **수정 §6.2/§4**.
- **[MED] use_bracket_orders 누락 위험** — 에이전트 경로만 `True`(`main.py:413`), 헬퍼는 `False`(`:506`).
  overlay/allowlist에 넣으면 bracket 보호 꺼짐. **수정 §5**: per-site 명시 + 테스트.
- **[MED→설계변경] CLAUDE.md durable** — `journal.py:123` write-once라 기존 워크스페이스는 옛 보수문구 유지.
  중립화 대신 **balanced=빈 disposition(현행 바이트동일)** + conservative/aggressive만 delta 주입. **수정 §2.2/2.3**.
- **[LOW] 문서 불일치** conservative max_open_positions 10↔8 → **8로 통일**(requirements §4 + FD §2.1).
- **검증된 정확 주장**(재검토 불요): balanced 리스크 9개 값 = 현행 settings.yaml 동일; 8개 빌더 전부 존재
  + 호출부 라인 일치; `debate_prompt` 제외 정상; restamp 배치거부 caveat 정확; `maybe_rollback` starvation 안전.

## 12. Critic 3차 적대 검토 (2026-06-16, 새 영역) — 엔지니어링 보강 직접 반영 + 정책 2건
> 1·2차 수정의 정합성 검증 + 미탐 영역. 4건 엔지니어링 보강 직접 반영, 2건 HIGH는 §12.2 사용자 결정.

### 12.1 엔지니어링 보강 (직접 반영)
- **fetch 윈도우 잔여 갭** — round-trip `closed_at`이 `latest+horizon` 초과 가능 → fetch end에
  `max(closed_at), today` 포함. **§6.1 수정.**
- **decision_index 불변식** — 파싱-성공 enumerate 인덱스, append-only·무삭제일 때만 안정 → grade 레코드에
  `ts` 저장 + 재읽기 교차검증 fail-safe skip. **§6.2 수정.**
- **캘리브레이션 경로 분리** — `stop_loss_pct`/`take_profit_pct`는 에이전트 bracket 경로 미사용(폴링백업/
  simple만); agent 경로는 `default_risk_reward`/`atr_stop_multiple`이 operative. 모순 아님. **§2.1 주석.**
- **PBT 정직화** — 단조성은 3-프로필 example assert, 진짜 생성형은 resolve fail-safe·maturity 경계. **§10 수정.**
- **1·2차 수정 검증 통과**: human 제외가 round-trip 매칭 안전(round-trip은 fills 기반 `trades.py`,
  decision source 무관); grade-write 데몬 EOD 전용 invariant 정확; use_bracket_orders per-site 정확.

### 12.2 HIGH — 사용자 결정 (UAQ 2026-06-16, 확정)
- **[HIGH-1] 확정: aggressive=단기 스윙(grading_horizon_days 2→3).** 같은날 스캘프 학습은 C2-full 후속,
  FD 정직 스코프(§2.1 표 + §6.2). aggressive는 거래는 단타·학습은 1~3일 스윙으로 확보.
- **[HIGH-2] 확정: excess per-day 정규화**(§6.2). 버킷 전 `excess / max(holding_days,1)`로 horizon 비교가능,
  win_rate 불변. 기존 F62 선재 한계 동반 개선; efficacy 의미가 per-day로 바뀜 → release note.
