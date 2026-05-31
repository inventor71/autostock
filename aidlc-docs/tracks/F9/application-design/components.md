# F9 — Components

> Application Design. 결정: Q1=A(신규 `place_order` verb), Q2=A(단순 주문만 replace),
> Q3=A(`force` 플래그), Q4=A(trailing_stop+ioc/fok 배선, opg/cls/oto stub-reject), Q5=A(notional→
> qty 환산 후 기존 sizer). 상세 비즈니스 로직은 Functional Design(per-unit)에서.

## C1. ConsoleOrderTools (U-CONSOLE, TS — `operator-console/src`)
- **목적**: opencode 운영자 AI에 노출되는 **구조화 Alpaca형 주문 tool 표면**. 단일 `steer` tool을
  주문 동사별 구조화 tool로 분리.
- **책임**:
  - `place_stock_order` / `cancel_order_by_id` / `cancel_all_orders` / `replace_order_by_id` /
    `close_position` / `close_all_positions` 6개 mutating tool을 zod inputSchema와 함께 등록.
  - 각 tool은 opencode permission(`autostock_<tool>:"ask"`)로 휴먼 컨펌 후에만 실행.
  - tool args를 검증(zod 경계, SECURITY-13/NFR-2)하고 `FileDrop.send(verb, args)`로 SteeringCommand
    파일드롭(+token). 토큰은 로그/결과에 노출 금지(SECURITY-03).
  - 안전/lifecycle/approval/context 동사는 **결정적 경로 유지**(트림된 parser.ts 또는 verb-name
    직접 tool) — LLM 해석에 안 맡김(FR-2 하이브리드).
- **인터페이스**: MCP stdio server(`mcp-server.ts`), 핸들러(`steer-handler.ts`), zod 스키마+계약
  상수(`schema.ts`), 파일드롭(`filedrop.ts`, 기존).
- **비책임**: 리스크 판정/사이징/주문 구성(데몬 권위). 읽기 경로(`steer_read`)는 무변경.

## C2. SteeringContract (U-DAEMON/U-CONSOLE 공유 — 교차언어 계약)
- **목적**: TS↔pydantic 와이어 계약. verb 집합 + envelope + **per-verb 주문 args 스키마**.
- **책임**:
  - `SteeringVerb`에 주문/관리 동사 추가: `place_order`, `replace_order`, `cancel_all`,
    `close_position`, `close_all`. (기존 18 verb 유지; buy/sell은 결정적 shorthand로 잔존 가능)
  - `place_order` args 스키마를 양 언어에 고정(`contract.json` 확장) — parser의 주문 문법 제거
    **전에** 선행(NFR-3). 드리프트(예: `trail_percent` vs `trail_pct`)를 테스트로 차단.
  - envelope(`id/ts/verb/args/confirmed/token/source`)는 불변.
- **인터페이스**: `records.py`(pydantic, authoritative), `schema.ts`(TS mirror),
  `contract/contract.json`(golden), 계약 테스트 양쪽.

## C3. SteeringCommandHandler (U-DAEMON, Py — `src/agent/steering/commands.py`)
- **목적**: 파일드롭된 SteeringCommand를 데몬 측에서 디스패치/실행.
- **책임**:
  - 신규 핸들러 `_v_place_order` / `_v_replace_order` / `_v_cancel_all` / `_v_close_position` /
    `_v_close_all`. 기존 `_v_buy`/`_v_sell`는 결정적 shorthand 경유 시에도 **동일 게이트**로 합류.
  - 주문 args → `Order` 초안 구성 → `RiskManager.receive_human_order(order, force=...)` 호출 →
    통과 시 `Broker.submit_order`/관리 메서드, reject 시 구조화 outcome(FR-6) emit.
  - 시장 개장/오프아워 큐잉, 심볼 락, reconcile 트리거 등 기존 부수효과 보존.
  - 안전동사(`_v_kill`/`_v_flatten`/`_v_halt_entries`/…) 결정적 디스패치 보존.
- **비책임**: 리스크 한도 판단(C5에 위임), 브로커 통신 세부(C6).

## C4. OrderModel (U-RISK, Py — `src/core/models.py` + `types.py`)
- **목적**: Alpaca 전체 주식 주문을 표현하는 도메인 모델.
- **책임**:
  - `OrderType`에 `TRAILING_STOP` 추가; `OrderClass`에 `OTO` 추가(단 v1 oto는 상위에서 reject).
  - `Order`에 필드 추가: `notional: float|None`, `extended_hours: bool`, `client_order_id: str|None`,
    `trail_price: float|None`, `trail_percent: float|None`.
  - validator 확장: trailing_stop엔 trail_price XOR trail_percent; notional은 market+day 전용
    (FR-7) & qty와 상호배타; bracket/oco 양 leg 필수(기존).
- **인터페이스**: pydantic `Order`.

## C5. HumanOrderRiskGate (U-RISK, Py — `src/risk/manager.py`)
- **목적**: 완전 지정 휴먼 주문을 받는 **신규 수신 게이트**(현재 휴먼 경로 무게이트 정정, FR-5).
- **책임** (validator + auto-protect 하이브리드, Q2/Q3/Q5 반영):
  - caller 지정 order_type/price/TIF/class **존중**.
  - budget/pool/breaker 검사(`max_open_positions`/no-add/`_new_buys_halted`/sizer) — `force=true`면
    이 검사만 우회(override 로그). price-sanity·자동보호는 우회 불가.
  - qty/notional 예산 초과 시 clamp 또는 reject + **pass-able 제안**(FR-6).
  - notional은 현재가로 qty 환산 후 기존 sizer 적용(Q5=A).
  - stop_loss/take_profit 누락 시 ATR/level 자동 보호 부착(`_resolve_stop` 재사용).
  - price-sanity(롱 스톱 ≥ 시장가 등) 위반 reject.
- **인터페이스**: 신규 `receive_human_order(order, *, force) -> OrderDecision`(통과 Order | 구조화
  Reject). 기존 `evaluate_signal`(에이전트 경로)는 **무변경**(회귀 방지) — 공유 헬퍼만 재사용.

## C6. AlpacaBrokerOrders (U-RISK, Py — `src/execution/brokers/alpaca_broker.py` + `base.py`)
- **목적**: 확장 `Order`를 Alpaca 요청으로 매핑 + 신규 주문관리 원시 메서드.
- **책임**:
  - `_build_request` 확장: trailing_stop(`TrailingStopOrderRequest`), notional, extended_hours.
  - `_time_in_force` 수정: 미지원 TIF(opg/cls 및 미배선) → **explicit reject**(무음 DAY 강등 제거,
    잠복버그 정정). ioc/fok 배선.
  - 신규 메서드: `replace_order(order_id, changes)`(Q2=A: 단순 주문만, bracket/oco leg 보유 시
    reject), `cancel_all_orders([symbol])`, `close_all_positions()`. `BaseBroker`에 시그니처 추가
    (시뮬/백테스트는 기본 no-op/loop).
- **인터페이스**: `BaseBroker` 추상 + `AlpacaBroker` 구현 + `SimulatedBroker` 보수적 기본.
