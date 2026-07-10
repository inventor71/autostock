# F96 Requirements — 진입 실행 가드 + 뉴스 신선도/priced-in

**Depth**: Standard · **Type**: brownfield feature · **Status**: DRAFT (승인 대기)

## 1. Intent

리서치 턴의 결정과 실제 브로커 체결 사이의 간극에서 발생하는 두 가지 손실 원인을 좁힌다.

- **문제 A (execution drift)**: 모멘텀 진입(LLM entry ≥ 현재가)은 현재 MARKET 주문으로
  나가고(`src/risk/manager.py:280` `use_limit = entry < price`, `:291`), executor는 실행
  시점 현재가를 **사이징에만** 쓰고 결정가 대비 얼마나 벌어졌는지 검사하지 않는다
  (`src/agent/executor.py:266`). research→execution ~50분 간격 동안 가격이 stop 쪽으로
  달아나도 그대로 체결된다.
- **문제 B (priced-in catalyst)**: news 툴은 `published_at`을 **원시 ISO로만** 반환하고 age를
  계산하지 않는다(`src/agent/tools/market.py:237`). 프롬프트엔 "이미 하루 지난 촉매는
  priced-in일 수 있다"는 경계가 전혀 없고, aggressive posture는 오히려 same-week catalyst를
  favor하라고 명시한다(`src/agent/aggressiveness.py:84`). → 발표 다음날 고점 근처 뒤늦은 진입.

## 2. In / Out of Scope

**In**
- FR-1 진입 실행 드리프트 가드 (BUY, 그리고 SELL_SHORT 진입).
- FR-2 news 툴에 `age_hours` + `priced_in_risk` 노출.
- FR-3 프롬프트/레슨에 priced-in 할인 규칙 추가 (aggressiveness 문구와 정합).

**Out** (이번 트랙 제외)
- 최소 ATR stop 거리 floor (#2) — 별도 트랙.
- `execute_pending` 주기 단축 / time-lag 튜닝 (#1) — knob 조정, 별도.
- 신규 시세 스트리밍/실시간 소스.

## 3. Functional Requirements

### FR-1 — Execution drift guard  【확정: LIMIT 강등 · 0.5 ATR · anchor=ref_price(옵션 B)】
> **구현 중 재결정 (사용자 승인)**: 최초 "anchor=entry, 없으면 skip" 안은 **near-no-op**임이
> 코드로 드러남 — entry(=`d.limit`)가 있으면 기존 `use_limit=entry<price`가 상방 드리프트를 이미
> buy-the-dip LIMIT@entry로 캡하고, entry가 없으면(=순수 market 진입, 정작 주 타겟) 앵커가 없어
> 가드 미발동. 그래서 **결정시각 가격 `ref_price`를 앵커로 삼는 옵션 B**로 전환.
- **FR-1.1 배치**: 가드는 **RiskManager의 진입 주문타입 로직**(`_build_bracket_buy` /
  `_build_bracket_short`)을 확장. anchor 판정 후 MARKET→LIMIT 강등.
- **FR-1.2 anchor**: `entry`(= LLM `d.limit`)가 있으면 그것, 없으면 **`ref_price`**(결정시각 가격).
  - `ref_price`는 `orchestrator._stamp_new`가 턴 직후(실행 lag 전) market 진입(BUY/SELL_SHORT,
    `limit=None`)에만 스탬프 → 학습-critical Decision에 **additive** 필드(legacy=None, grading 무영향).
  - 배선: `Decision.ref_price` 필드 · `AgentTradingLoop(price_provider=…)` 주입 ·
    `main.py`가 `data_provider.get_latest_price` 연결 · `executor._to_signal`이 metadata로 전달.
  - entry·ref_price 모두 없으면 가드 미적용(기존 MARKET — fail-honest).
- **FR-1.3 판정·동작 (LIMIT 강등, 단일 knob)**:
  - `slip = guard_max_slippage_atr * atr` (기본 `guard_max_slippage_atr = 0.5`).
  - **BUY**: 현재가 `price > entry + slip` 이면 MARKET 대신 **LIMIT @ round(entry + slip)** 로 제출.
    (달아났으면 미체결, 밴드 내로 눌리면 체결 — 최악 체결가 = entry+0.5 ATR로 상한.)
  - **SELL_SHORT**: 대칭 — `price < entry - slip` 이면 **LIMIT @ round(entry - slip)**.
  - `atr` 결측(=None) 시 가드 미적용(기존 동작). 기존 buy-the-dip(`entry < price`) LIMIT 경로는 불변.
- **FR-1.4 무회귀**: `price ≤ entry + slip`(정상 범위)이면 기존과 바이트-동일(MARKET/LIMIT 그대로).
- **FR-1.5 로그**: 강등 발생 시 기존 `logger.info`(Risk approved 라인)에 `guard=drift-capped` 표기 +
  executor의 `execution_outcomes.jsonl` outcome detail로 추적(주문 order_type=LIMIT로 이미 구분됨).
- **FR-1.6 설정**: `guard_max_slippage_atr`는 config로 조정 가능(하드코딩 금지 — risk config 선례).

### FR-2 — News freshness surface
- **FR-2.1** `news()` 반환의 각 항목에 `age_hours`(발행~현재, float, tz-safe) 추가. `published_at`
  없으면 `None`(fail-honest).
- **FR-2.2** 항목 수준에 `priced_in_risk` 플래그 추가 【확정: 조언용, age 기반 단독】.
  정의: `age_hours`가 임계(기본 24h) 초과면 `"elevated"`, 이하면 `"fresh"`, 발행일 결측이면 `None`.
  순수 age 기반(가격변동 결합·가드 연동은 범위 밖 — priced-in 판단은 LLM 재량).
- **FR-2.3** 순수/결정론적 계산(주입 클럭으로 테스트 가능) — `Date.now` 직접 호출 지양, 기존 패턴 준수.

### FR-3 — Prompt / lesson rule
- **FR-3.1** 진입 가이드에 "촉매가 24h(설정값) 초과 + 진입가가 20d high 근처면 priced-in 위험을
  가중, 확신 없으면 보류" 규칙 추가.
- **FR-3.2** `aggressiveness.py`의 same-week catalyst 선호와 모순되지 않게 조정
  (선호는 유지하되 "이미 급등·priced-in" 예외를 명시).

## 4. Non-Functional
- **NFR-1 무회귀**: 임계 미달 시 기존 동작 바이트-동일. 기존 executor/RiskManager 테스트 그린 유지.
- **NFR-2 Fail-honest**: 앵커/시세/발행일 결측은 가드·플래그를 **끄되(진입 차단 아님)** 로그로 남긴다.
- **NFR-3 Idempotency**: 보류(defer) 시 cursor 규칙이 무한 stall 없이 다음 턴 재평가 되도록
  (`skipped_drift`는 non-terminal, 기존 no_order/error와 동일 취급).
- **NFR-4 결정론 테스트**: age 계산·드리프트 판정은 주입 클럭/시세로 단위테스트.

## 5. Resolved Decisions (UAQ 확정 — 2026-07-07)
1. **가드 동작**: **LIMIT 강등** (MARKET → anchor+슬리피지밴드 LIMIT). defer 미채택.
2. **가드 임계**: **ATR 배수, 기본 0.5 ATR** (`guard_max_slippage_atr = 0.5`). 단일 knob = 트리거이자 체결 상한.
3. **#3 성격**: **조언용 노출 + 프롬프트 규칙만**. priced-in의 가드 연동은 미채택(인위적 결합 회피).
4. **Extensions**: **둘 다 미적용** — Security Baseline N/A(신규 외부 입력/공격 표면 없음),
   Property-Based Testing 미적용(예제 기반 단위테스트로 충분).

## 6. Acceptance Criteria (초안)
- AC-1 anchor 대비 임계 초과 역드리프트 BUY가 회피 동작으로 전환되고 `execution_outcomes.jsonl`에 기록.
- AC-2 임계 미달 진입은 기존과 동일하게 MARKET/LIMIT 제출.
- AC-3 `news()` 출력에 `age_hours`/`priced_in_risk`가 tz-safe·fail-honest로 채워짐.
- AC-4 프롬프트에 priced-in 규칙 존재, aggressiveness 문구와 무모순.
- AC-5 신규 단위테스트(가드 판정·age 계산) 그린 + 기존 스위트 회귀 없음.
