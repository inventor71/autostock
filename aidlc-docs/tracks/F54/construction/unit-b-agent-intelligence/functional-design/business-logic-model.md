# Unit B: Agent Intelligence — Functional Design

> **Track**: F54 / Unit B
> **Phase**: Functional Design
> **Date**: 2026-06-04
> **Goal**: LLM 에이전트가 숏 기회를 분석(FR-6)하고 의사결정(FR-7)하게 한다. Unit A의
> 주문 파이프라인 위에 분석/프롬프트/운영 표시 계층을 얹는다.

## Scope note
Unit A로 숏 주문 실행 경로(decisions.jsonl → executor → RiskManager → broker)는 이미
완성됨. 따라서 에이전트는 `SELL_SHORT`/`BUY_TO_COVER` 결정을 쓰기만 하면 숏을 칠 수 있다.
Unit B는 (1) 숏 분석 데이터를 에이전트에 공급, (2) 프롬프트가 숏을 고려/결정하도록 지시,
(3) 운영자에게 숏 포지션을 정확히 표시한다.

---

## BLM-1: 숏 분석 도구 (FR-6, Q5=B)

### market.short_data(symbol) — 신규
yfinance `Ticker.info`에서 숏 관련 필드를 추출하고 위험 플래그를 계산.

```
short_data(symbol) → {
    symbol,
    short_percent_of_float,   # shortPercentOfFloat (유통주식 대비 공매도 %)
    short_ratio,              # shortRatio (days-to-cover)
    shares_short,             # sharesShort
    shares_short_prior,       # sharesShortPriorMonth (추세)
    short_interest_change_pct,# (current - prior) / prior
    borrow_availability,      # "검증 필요 — yfinance 미제공; locate는 Alpaca 주문 시점 확인"
    squeeze_risk,             # 계산된 플래그: "HIGH" if short_float > 40 else "ELEVATED" if >20 else "LOW"
    note,                     # 사람이 읽는 경고 문자열
}
```

**위험 플래그 (FR-6.3, NFR-1.3)**: `short_percent_of_float > 40%` → `squeeze_risk="HIGH"` +
경고 노트. 자동 거부는 하지 않음(과잉 제한 우려) — 에이전트/운영자 판단용 신호로만 전달.

**대차(borrow) 데이터 현실 (Q5=B 결정의 데이터 소스)**: yfinance는 borrow rate / locate를
제공하지 않음. Alpaca paper는 주문 시점에 대차 가능 여부를 판정(주문 거부로 표면화). 따라서
`short_data`는 short interest 계열을 제공하고, borrow availability는 "주문 시점 Alpaca가
판정"으로 명시 — 잘못된 자신감을 주지 않는다(fail-honest).

### tools/__main__.py — `short_data` 서브커맨드 추가
`python -m src.agent.tools short_data <SYMBOL>` → JSON.

---

## BLM-2: account 도구 숏 인식 (FR-11 데이터)

`market.account()`의 포지션 dict 수정:
- `side` 필드 추가 ("long"/"short")
- `unrealized_pct` 부호 수정: 숏은 `(avg_entry/price - 1)*100` (가격 하락 → 양수)
  현재는 `(price/avg_entry - 1)*100`로 롱 전용 → 숏에서 부호 반대로 나옴

```
positions[i] = {
    "symbol", "side",                 # ← side 신규
    "qty", "avg_entry", "price",
    "unrealized_pnl",                 # Unit A에서 이미 부호 정확 (Position.update_price)
    "unrealized_pct",                 # ← 방향 인식으로 수정
    "market_value",
}
```

---

## BLM-3: 스냅샷 퍼블리셔 숏 노출 (FR-11, TUI 데이터)

`steering/runtime.py`의 `publish_snapshot`이 포지션을 직렬화하는 곳에 `side` 추가.
TUI(opencode fork)는 이 스냅샷을 읽어 L/S 마커를 렌더 — Python은 데이터만 노출하고,
TS 렌더링은 후속(별도 언어 surface).

---

## BLM-4: 프롬프트 숏 확장 (FR-7, Q7=A Full LLM)

### prompts.morning_research_prompt
- Discovery 섹션에 숏 후보 발굴 지시 추가: "과대평가/기술적 약세/악재 모멘텀 종목도 숏
  후보로 평가. 숏 후보엔 `short_data`로 숏 스퀴즈 위험을 반드시 확인."
- 결정 작성: "숏 진입은 `SELL_SHORT` (반드시 stop 포함 — 없으면 executor가 거부). 청산은
  `BUY_TO_COVER`."

### prompts.intraday_prompt / wake_prompt
- brief에 숏 포지션도 포함됨(held_symbols는 symbol 키라 자동). 숏 손절/익절 방향 안내 추가.

### prompts.eod_review_prompt (해당 함수 존재 시)
- 숏 포지션 일일 P&L + 숏 스퀴즈 위험 재평가 + (대차 비용 인식) 항목 추가.

### _ADVISOR_REMINDER
변경 없음(advisor-only 불변).

---

## BLM-5: workspace CLAUDE.md 숏 규칙 (FR-7.5)

`src/agent/templates/CLAUDE.md`에 "Short Selling Rules" 섹션 추가:
- 숏은 반드시 stop 포함 (무제한 손실 방어)
- short_float > 40% 경계 (스퀴즈)
- 액션 스키마: SELL_SHORT(stop 필수)/BUY_TO_COVER(cover_pct=sell_pct)
- 방향 전환: 롱 보유 중 SELL_SHORT → executor가 자동 청산 후 숏 (수동 청산 불필요)

---

## BLM-6: 휴먼 스티어링 숏 (FR-9, Python 측)

`steering/records.py::PlaceOrderArgs.side`: `Literal["buy","sell"]` →
`Literal["buy","sell","sell_short","buy_to_cover"]`.

`steering/commands.py::_order_from_place_args`: `OrderSide(args.side)`가 이미 값 매핑하므로
side 확장만으로 SELL_SHORT/BUY_TO_COVER Order 생성 → 이미 확장된 `receive_human_order`
(Unit A)가 게이팅. 추가 매핑 로직 불필요.

운영자 TUI(opencode)의 `/short`·`/cover` 표층 명령은 TS fork 변경 — **후속 항목**으로 분리
(이 트랙은 Python 계약까지; place_order(side=sell_short)로 이미 기능적으로 가능).

---

## Out of Scope (Unit B)
- opencode TS TUI의 L/S 마커 시각 렌더링 + `/short`·`/cover` 표층 명령 (별도 언어 surface,
  데이터/계약은 본 트랙에서 노출)
- 기술적 전략 숏 시그널 (Q8=D, 후속 트랙)

## Testable Properties (PBT-01)
| Component | Property | Category |
|-----------|----------|----------|
| account() short unrealized_pct | 숏: price < entry → pct > 0 | Invariant |
| short_data squeeze_risk | short_float>40 → "HIGH" | Oracle |
| PlaceOrderArgs round-trip | sell_short/buy_to_cover JSON 왕복 | Round-trip |
