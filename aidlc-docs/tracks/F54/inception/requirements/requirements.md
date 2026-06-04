# F54 — 숏 포지션 기능 요구사항

> **Track**: F54
> **Phase**: Requirements Analysis
> **Depth**: Standard~Comprehensive (시스템 전반 변경, 리스크 민감)
> **Date**: 2026-06-04
> **언어**: 한국어

---

## 1. Intent Analysis

### 1.1 사용자 요청 (원문)
> "숏기능이 필요해. 장이 안좋으면 롱 포지션만 유지하는건 말이 안됨. 장의 균형에 맞춰서 숏을 가능하게 하고, 숏을 위한 분석도 가능해야 함"
>
> 추가: "숏의 위험이 있으니, 이 부분을 이번 트랙에서 어떻게 고려할지 생각해서 진행"

### 1.2 요청 유형
- **Type**: New Feature
- **Scope**: System-wide (core → risk → execution → agent, 약 15개 파일)
- **Complexity**: Complex (리스크 로직 방향 반전, 다중 서브시스템 변경, 무제한 손실 위험)

### 1.3 핵심 의도
1. 하락장에서도 수익 창출 가능한 숏 포지션 운영
2. 시장 방향성에 균형 잡힌 포지션 구성
3. 숏을 위한 LLM 에이전트 분석 역량 확보
4. **숏 특유의 위험(무제한 손실, 숏 스퀴즈, 대차 비용)에 대한 방어 체계 내재화**

---

## 2. 사용자 설계 결정 (Requirements Analysis Questions)

| Q | 영역 | 결정 | 근거 |
|---|------|------|------|
| Q1 | 포지션 모델 | **C** — 한 방향만, 자동 청산 후 반대 진입 | 심볼당 단일 포지션 유지 + 필요시 방향 전환 |
| Q2 | 액션 명명 | **A** — SELL_SHORT / BUY_TO_COVER | Alpaca API 1:1 매핑, 감사 추적 명확 |
| Q3 | 리스크 파라미터 | **C** — 공유 + settings.yaml 오버라이드 | 기존 U2 패턴 재사용 |
| Q4 | 서킷 브레이커 | **B** — 개별 (롱/숏 각각) | 급락→롱 차단, 급등→숏 차단 |
| Q5 | 분석 도구 | **B** — 표준 (short interest + 대차/비용) | 대차 불가 블로커 방지 |
| Q6 | 백테스트 | **C** — 제외 (라이브/페이퍼만) | 이번 트랙 스코프 제한 |
| Q7 | LLM 숏 | **A** — Full LLM (분석+결정) | "숏을 위한 분석도 가능해야 함" 직결 |
| Q8 | 기술적 전략 | **D** — 추후 트랙 | F54 스코프에서 제외 |
| Q9 | TUI | **A** — L/S 마커 + P&L 반전 | 최소한의 시각적 구분 |
| Q10 | Security | **A** — Enabled | 기존 프로젝트 컨벤션 |
| Q11 | PBT | **B** — Partial (Hypothesis) | 순수 함수 + 직렬화 |

---

## 3. Functional Requirements

### FR-1: 숏 포지션 진입 (SELL_SHORT)

**FR-1.1** 시스템은 `SELL_SHORT` 액션을 통해 새로운 숏 포지션을 진입할 수 있어야 한다.

**FR-1.2** `SELL_SHORT` 액션은 `DecisionAction`에 추가되며, `Signal.SELL_SHORT` → `OrderSide.SELL_SHORT` → Alpaca `sell_short`로 매핑된다.

**FR-1.3** 숏 진입은 RiskManager의 `evaluate_signal()`을 통과해야 한다 (롱과 동일한 게이트).

**FR-1.4** 숏 진입 시 반드시 손절가(`stop_loss_price`)가 설정되어야 한다. 손절가 없는 숏 진입은 거부된다 (Fail-closed — SECURITY-15). *숏 무제한 손실 위험 방어.*

**FR-1.5** 숏 브라켓 오더는 진입가 **위**에 손절, 진입가 **아래**에 익절이 위치한다 (롱의 반대).

### FR-2: 숏 포지션 청산 (BUY_TO_COVER)

**FR-2.1** 시스템은 `BUY_TO_COVER` 액션을 통해 숏 포지션을 청산(커버)할 수 있어야 한다.

**FR-2.2** `BUY_TO_COVER`는 `DecisionAction`에 추가되며, `Signal.BUY_TO_COVER` → `OrderSide.BUY_TO_COVER` → Alpaca `buy_to_cover`로 매핑된다.

**FR-2.3** 부분 커버 지원: `sell_pct` (또는 `cover_pct`) 파라미터로 숏 포지션의 일부만 커버 가능.

### FR-3: 자동 방향 전환 (Q1=C)

**FR-3.1** 롱 보유 중 `SELL_SHORT` 시그널 수신 시: 기존 롱을 전체 청산(SELL)한 후 숏 진입. 청산이 실패하면 숏 진입도 중단된다.

**FR-3.2** 숏 보유 중 `BUY` 시그널 수신 시: 기존 숏을 전체 커버(BUY_TO_COVER)한 후 롱 진입. 커버가 실패하면 롱 진입도 중단된다.

**FR-3.3** 부분 청산 후 남은 수량으로 반대 방향 진입은 지원하지 않는다 (복잡성 관리). 항상 전체 청산 → 신규 진입.

**FR-3.4** 방향 전환은 두 개의 독립된 오더로 실행되며, 각각 execution log에 기록된다.

### FR-4: 숏 리스크 관리

#### FR-4.1: 필수 손절 (Mandatory Stop-Loss)
**FR-4.1.1** 모든 숏 진입은 반드시 `stop_loss_price`를 가져야 한다. 손절가가 없으면 RiskManager가 거부한다.
**FR-4.1.2** 숏 손절은 반드시 진입가보다 높아야 한다 (`stop_loss_price > entry_price`). 위반 시 `PRICE_SANITY`로 거부.
**FR-4.1.3** 숏 손절가와 진입가의 차이(`stop_loss_pct`)는 `max_stop_distance_pct`를 초과할 수 없다 (과도한 리스크 방지).

#### FR-4.2: 숏 익절 (Take-Profit)
**FR-4.2.1** 숏 익절은 진입가보다 낮아야 한다 (`take_profit_price < entry_price`).
**FR-4.2.2** 기본 risk-reward 비율은 `default_risk_reward`를 동일하게 사용한다 (진입가 - RR × (손절가 - 진입가)).

#### FR-4.3: 숏 손절 래칫 (Stop Ratchet)
**FR-4.3.1** 숏 손절은 아래로만 조정된다 (타이트하게). `ratchet_stop(current, proposed) → min(current, proposed)`.
**FR-4.3.2** 롱과 반대 방향: 롱 래칫은 `max` (위로), 숏 래칫은 `min` (아래로).

#### FR-4.4: 숏 폴드 백업 (Polled Exits)
**FR-4.4.1** `check_stop_loss()`: 숏 포지션의 손절 조건 = `(current_price - avg_entry_price) / avg_entry_price >= stop_loss_pct`.
**FR-4.4.2** `check_take_profit()`: 숏 포지션의 익절 조건 = `(avg_entry_price - current_price) / avg_entry_price >= take_profit_pct`.

#### FR-4.5: 숏 포지션 사이징
**FR-4.5.1** 숏 진입 시 `calculate_shares()`는 동일한 예산 로직을 사용하되, 손절 퍼센트를 양수로 변환하여 전달한다.
**FR-4.5.2** 숏 마진 요구사항: `PortfolioState.cash` 대비 여유 자본 확인. `settings.yaml`의 `short.max_position_pct` 또는 `max_position_pct`를 오버라이드로 사용.

### FR-5: 서킷 브레이커

**FR-5.1** 기존 `_new_buys_halted` 유지 (롱 진입 차단). `market_halt_threshold_pct` 이하 SPY 하락 시 발동.

**FR-5.2** `_new_shorts_halted` 추가 (숏 진입 차단). `short_market_halt_threshold_pct` 이상 SPY 상승 시 발동 (기본값: +0.03, 즉 3% 이상 급등 시 숏 진입 차단).

**FR-5.3** `config/settings.yaml`의 `risk.short_market_halt_threshold_pct`로 설정 가능.

**FR-5.4** 개별 종목 서킷 브레이커: 당일 종목 가격이 10% 이상 급등한 종목에 대한 신규 숏 진입은 거부된다 (숏 스퀴즈 방어).

### FR-6: 숏 분석 도구 (Q5=B)

**FR-6.1** 기존 `fundamentals` 도구에 다음 필드 추가:
- `short_interest`: 공매도 잔고 (주식 수)
- `short_float`: 유통주식 대비 공매도 비율 (%)
- `days_to_cover`: 평균 거래량 기준 숏 커버 소요일

**FR-6.2** 신규 `short_data` 도구 (또는 `fundamentals` 확장):
- `borrow_rate`: 대차 이자율 (연율 %)
- `locate_available`: 대차 가능 여부 (boolean / descriptive)
- 데이터 소스: yfinance (무료, 커버리지 넓음), Alpaca (계정 필요), web search (백업)

**FR-6.3** 위험 플래그: `short_float > 40%`인 종목은 "High Short Interest" 경고가 분석 결과에 포함된다. 에이전트 프롬프트에 해당 종목의 숏 스퀴즈 위험을 명시적으로 경고.

### FR-7: 에이전트 프롬프트 확장 (Q7=A)

**FR-7.1** Morning research turn: 유니버스 스캔 시 숏 후보도 발굴하도록 지시. "과대평가된 종목, 기술적 약세, 악재 뉴스" 등의 숏 시그널을 찾도록 프롬프트 추가.

**FR-7.2** Intraday turn: 숏 포지션의 손절/익절 레벨을 롱과 동일한 brief에 포함.

**FR-7.3** EOD review: 숏 포지션의 일일 P&L, 대차 비용 추정, 숏 스퀴즈 위험 재평가 포함.

**FR-7.4** Decisions.jsonl: 숏 진입 시 thesis 파일에 "short thesis" 섹션 포함 (롱과 구분).

**FR-7.5** `workspace/CLAUDE.md`에 숏 트레이딩 규칙 섹션 추가: 필수 손절, 숏 스퀴즈 경계, 대차 비용 인식.

### FR-8: 실행 파이프라인

**FR-8.1** `DecisionExecutor._to_signal()`: `SELL_SHORT → Signal.SELL_SHORT`, `BUY_TO_COVER → Signal.BUY_TO_COVER` 매핑.

**FR-8.2** `DecisionExecutor.execute_decision()`: `SELL_SHORT`에 대해 자동 방향 전환(FR-3) 체크.

**FR-8.3** `DecisionExecutor._place_protection()`: 숏 포지션의 OCO 보호는 `OrderSide.BUY_TO_COVER`로 매핑 (롱은 `OrderSide.SELL`).

### FR-9: 휴먼 스티어링 숏 명령

**FR-9.1** `/short SYM <N$|Nsh>` — 숏 포지션 진입 (human steering console).

**FR-9.2** `/cover SYM <N%|Nsh>` — 숏 포지션 청산/커버.

**FR-9.3** Human 숏 명령도 RiskManager의 `receive_human_order()`를 통과하며, 필수 손절 규칙(FR-4.1)이 적용된다.

### FR-10: 데이터 모델 확장

**FR-10.1** `Position` 모델에 `side: PositionSide` 필드 추가 (기본값 `LONG`).

**FR-10.2** `Position.update_price()`: 숏 포지션의 P&L 계산 수정.
- Long: `unrealized_pnl = market_value - cost_basis` (현행)
- Short: `unrealized_pnl = cost_basis - market_value` (반전)

**FR-10.3** `Order` 모델: 기존 validator에 숏 bracket 검증 추가 (`order_class == BRACKET && side == SELL_SHORT` → `stop_loss_price > limit_price`, `take_profit_price < limit_price`).

**FR-10.4** `DecisionAction`: `"BUY" | "SELL" | "HOLD" | "ADJUST_STOP"` → `"BUY" | "SELL" | "HOLD" | "ADJUST_STOP" | "SELL_SHORT" | "BUY_TO_COVER"`.

**FR-10.5** `Signal` enum에 `SELL_SHORT`, `BUY_TO_COVER` 추가.

**FR-10.6** `OrderSide` enum에 `SELL_SHORT`, `BUY_TO_COVER` 추가.

### FR-11: TUI 표시 (Q9=A)

**FR-11.1** 포지션 목록에 `[L]` / `[S]` prefix로 롱/숏 구분.

**FR-11.2** 숏 포지션의 P&L 색상 반전: 가격 하락 → 녹색(수익), 가격 상승 → 적색(손실).

---

## 4. Non-Functional Requirements

### NFR-1: 안전성 (Safety) — 숏 특유 위험 방어

**NFR-1.1 Fail-Closed (SECURITY-15)**: 모든 숏 관련 검증은 실패 시 기본적으로 거부한다.
- 손절가 누락 → 거부
- 손절가 방향 오류 → 거부
- 대차 불가 종목 → 거부 (경고와 함께)
- 당일 10%+ 급등 종목 → 거부

**NFR-1.2 Defense-in-Depth**: 숏 진입은 3중 방어를 통과해야 한다.
1. 에이전트/전략 레벨: 분석 도구의 위험 데이터 기반 의사결정
2. RiskManager 레벨: 필수 손절, 방향 검증, 사이즈 제한
3. Broker 레벨: Alpaca API의 숏 가능 여부 최종 확인

**NFR-1.3 Short-Squeeze Guard**: `short_float > 40%` 종목은 RiskManager가 아닌 **에이전트/운영자에게 경고**로 전달한다. 자동 거부는 하지 않지만(과잉 제한 우려), 에이전트 프롬프트에 경고가 주입된다.

### NFR-2: 신뢰성 (Reliability)

**NFR-2.1** 자동 방향 전환(FR-3)에서 청산 실패 시 상태 불일치가 없어야 한다: 청산 오더가 partial fill이면 남은 수량을 확인하고, 전체 미체결이면 방향 전환을 중단한다.

**NFR-2.2** Execution log(execution_outcomes.jsonl)에 모든 방향 전환 시퀀스를 개별 기록한다.

### NFR-3: 확장성 (Extensibility)

**NFR-3.1** `settings.yaml`의 `short_risk:` 블록을 통해 추후 숏 전용 파라미터 오버라이드가 가능해야 한다 (Q3=C).

**NFR-3.2** 기술적 전략(F55+)에서 `Signal.SELL_SHORT`를 생성할 수 있도록 Signal/OrderSide 체계가 준비되어야 한다.

### NFR-4: 테스트 용이성 (Testability)

**NFR-4.1 PBT (Partial, Hypothesis)**: 다음 순수 함수들에 property-based test 적용 (PBT-02, PBT-03):
- `RiskManager._resolve_short_stop()`: "항상 entry보다 위" invariant
- `Order._check_bracket_legs()`: 숏 bracket 검증 round-trip
- `Position.update_price()`: 숏 P&L 부호 invariant (가격↓ → P&L 양수)
- `Decision` / `Order` 모델 JSON round-trip (SELL_SHORT/BUY_TO_COVER 포함)

**NFR-4.2** SimulatedBroker에 숏 포지션 기본 지원 추가 (페이퍼 검증용).

### NFR-5: 보안 (Security)

**NFR-5.1 SECURITY-03**: 숏 주문 관련 로그에 API 키, 토큰, PII가 포함되지 않아야 한다.

**NFR-5.2 SECURITY-11**: 숏 리스크 로직(`_handle_sell_short`, `_resolve_short_stop` 등)은 RiskManager 내에 격리된다. 다른 모듈이 직접 손절가를 계산하지 않는다.

**NFR-5.3 SECURITY-15**: 모든 숏 관련 오류 경로는 명시적으로 처리되며, 기본값은 fail-closed(거부)이다.

---

## 5. 범위 제외 (Out of Scope)

| 항목 | 사유 |
|------|------|
| 백테스트 숏 지원 | Q6=C, 추후 트랙 |
| 기술적 전략 숏 시그널 (RSI, MACD 등) | Q8=D, 추후 트랙 |
| KIS 한국주식 숏 | Alpaca US 주식 먼저 |
| 롱/숏 동시 보유 (헤지) | Q1=C |
| Short Sale Restriction (SSR) 체크 | v1 제외, Alpaca가 자동 처리 |
| 옵션/선물 기반 숏 | 범위 초과 |
| 숏 buying_power 명시 게이트 | 후속 트랙(F55+). v1은 per-position equity 상한 + Alpaca 서버측 마진 거부에 의존 (critic #2, 사용자 결정 2026-06-04) |

---

## 6. 숏 특유 위험 — 트랙 내 대응 요약

| 위험 | 심각도 | 대응 방식 | 구현 위치 |
|------|--------|----------|----------|
| 무제한 손실 | 🔴 Critical | 필수 손절가 (Hard Stop) — 손절 없는 숏 진입 불가 | RiskManager FR-4.1 |
| 숏 스퀴즈 | 🟠 High | 40%+ short float 경고 + 10% 급등 종목 진입 차단 | 분석도구 FR-6.3 + 서킷브레이커 FR-5.4 |
| 대차 비용 | 🟡 Medium | 대차 이자율 분석 도구 + EOD 비용 리뷰 | 분석도구 FR-6.2 + 프롬프트 FR-7.3 |
| 증거금 부족 | 🟡 Medium | 포지션 사이저 보수적 적용 | PositionSizer FR-4.5 |
| 방향 전환 실패 | 🟠 High | 청산 완료 확인 후 진입 (all-or-nothing) | Executor FR-3.1/3.2 |
| Fail-Closed | 🔴 Critical | 모든 검증 실패 시 거부 | SECURITY-15 NFR-1.1 |

---

## 7. Key Architecture Decisions

1. **`Position.side` 필드 추가** — 기존 Position 모델을 최소한으로 확장하여 방향 구분
2. **`SELL_SHORT`/`BUY_TO_COVER` 신규 액션** — 모호한 컨텍스트 추론 없이 명시적 의도 표현
3. **자동 방향 전환은 executor에서** — RiskManager는 단일 시그널만 평가, executor가 시퀀싱 담당
4. **숏 손절은 structural requirement** — Alpaca 브라켓 오더의 stop_price로 exchange-side强制执行, polled backup은 보조
5. **백테스트 제외로 스코프 제한** — 라이브/페이퍼 경로에 집중하여 위험 방어 로직의 완성도를 높임
