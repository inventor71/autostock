# F9 — Application Design 계획 + 개방 설계 질문

> Workflow Planning 승인 후 작성. requirements.md(v3 + critic 반영) 기반. 실제 코드 표면을
> 읽고(아래 "코드 사실") 컴포넌트/메서드/계약 설계 초안을 정리하고, **아직 모호한 5개 설계
> 결정**을 [Answer] 태그로 남긴다. 답변 후 components.md / component-methods.md / services.md /
> component-dependency.md / application-design.md 산출물을 생성한다.
> **질문은 A/B/C 중 택1로 `[Answer]:` 옆에 기입.** (각 질문에 권장안을 표시했으니 그대로면 그
> 문자만 적어도 됨.)

---

## 코드 사실 (설계 근거, critic 검증 완료)

- **콘솔 MCP** (`operator-console/src/mcp-server.ts`): 현재 mutating tool은 단일 `steer({command:string})`
  하나. opencode가 tool 단위 permission(`autostock_steer:"ask"`)으로 휴먼 컨펌. `handleSteer`→
  `parseCommand`(parser.ts)→`FileDrop.send(verb,args)`. 구조화 tool화 = `registerTool`를 tool별로
  쪼개고 각자 zod inputSchema + permission 키를 갖게 함.
- **계약** (`schema.ts` ↔ `records.py` ↔ `contract/contract.json`): `ALL_VERBS`(18개 verb)·envelope
  필드만 고정. `args`는 free dict(`dict[str,Any]` / `Record<string,unknown>`) → **per-verb args는
  현재 미보호**. 새 verb 추가 시 records.py `Literal`, schema.ts `ALL_VERBS`, contract.json 동시 수정.
- **데몬 디스패치** (`commands.py`): `getattr(self, f"_v_{cmd.verb}")`. 새 verb엔 `_v_<verb>` 필요.
  휴먼 BUY(`_v_buy`→`build_human_buy`)는 qty floor + 스톱 부착만, **리스크 게이트 미경유**.
- **RiskManager** (`manager.py`): `evaluate_signal(signal,price,portfolio)`가 에이전트 경로의 게이트
  (max_open_positions / no-add / `_new_buys_halted` / `position_sizer.calculate_shares` /
  `_resolve_stop` clamp). 휴먼 경로는 이 함수를 안 씀.
- **Order** (`models.py`): symbol/side/qty/order_type/limit_price/stop_price/time_in_force(str,"day")/
  order_class/take_profit_price/stop_loss_price. validator는 bracket/oco에 양 leg 필수.
  trailing/notional/extended_hours/client_order_id 없음. `OrderType`=market/limit/stop/stop_limit,
  `OrderClass`=simple/bracket/oco (`types.py`).
- **브로커** (`base.py`): `submit_order(Order)->FilledOrder`, `cancel_order(order_id)`,
  `close_position(symbol)`, `get_open_orders([symbol])`, `get_order_status`. **replace_order /
  cancel_all_orders / close_all_positions 없음**(cancel_all/flatten은 commands.py에서 루프 에뮬).
  `_time_in_force`는 gtc 외 전부 DAY로 무음 강등.

---

## 설계 초안 (확정 전 — 질문 답변 후 산출물에 반영)

### 컴포넌트 / 메서드 표면 (잠정)
- **U-CONSOLE (TS)**: 주문 tool은 구조화 `registerTool`로 분리 — `place_stock_order`,
  `cancel_order_by_id`, `cancel_all_orders`, `replace_order_by_id`, `close_position`,
  `close_all_positions` (각자 zod schema + `autostock_*:"ask"` permission). 안전/lifecycle/approval/
  context 동사는 **결정적 경로 유지**(트림된 parser.ts 또는 verb-name 직접 tool). 각 주문 tool은
  `FileDrop.send(verb, args)`로 SteeringCommand 생성.
- **U-DAEMON (Py)**: `SteeringCommand` verb 집합 확장 + per-verb args 스키마(pydantic) 도입.
  `_v_place_order`(또는 `_v_buy`/`_v_sell` 확장 — Q1) / `_v_replace_order` / `_v_cancel_all` /
  `_v_close_position` / `_v_close_all`. 주문 핸들러는 RiskManager 수신 함수를 호출.
- **U-RISK (Py)**: `Order` 모델 확장(trailing/notional/extended_hours/client_order_id, `OrderType`+
  trailing_stop, `OrderClass`+oto). `AlpacaBroker._build_request`/`_time_in_force` 확장(미지원
  TIF/class → explicit reject). 신규 브로커 메서드(replace/cancel_all/close_all). RiskManager에
  **신규 수신 메서드** `receive_human_order(order, *, force) -> Order|Reject`(validate+budget/pool/
  breaker+clamp+auto-protect+price-sanity), 구조화 reject 결과 타입.

### 서비스/오케스트레이션
- 흐름: opencode AI → 구조화 tool → (opencode `ask`) → `FileDrop.send` → commands.jsonl(+token) →
  데몬 `CommandHandler._v_*` → `RiskManager.receive_human_order` → `Broker.submit_order` / 구조화 reject
  → events.jsonl outcome(제안 포함, FR-6).

---

## 개방 설계 질문 (A/B/C 택1)

### Q1. place_stock_order의 verb 매핑
구조화 주문을 데몬 계약에서 어떤 verb로 표현할까?
- **A.** 신규 단일 verb `place_order` (side를 args로) — Alpaca `place_stock_order` 1:1 미러(Q6=A와
  정합), 콘솔 tool명도 `place_stock_order`. 데몬 `_v_place_order` 신규. **(권장)**
- **B.** 기존 `buy`/`sell` verb를 리치 args로 확장 — `_v_buy`/`_v_sell` 디스패치 재사용, verb 집합
  변경 최소. 단 Alpaca 1:1 미러에서 살짝 벗어남.
- **C.** 기타(자유 기술).

[Answer]: A

### Q2. replace_order_by_id 의미론 (resting bracket/OCO leg 대상)
critic이 "leg-aware replace는 어렵다"고 지적. v1 범위는?
- **A.** v1에서는 **bracket/OCO leg를 가진 주문의 replace는 reject**, 단순(simple) 미체결 주문만
  Alpaca 네이티브 replace(qty/limit/stop 변경). bracket 조정은 cancel→재place로 안내. **(권장: 안전)**
- **B.** cancel-then-resubmit 방식으로 전부 처리(보호레그 포함 재구성) — 표현력↑이나 레이스/부분
  취소 위험.
- **C.** Alpaca 네이티브 PATCH replace를 leg까지 포함해 풀로 지원(가장 큰 작업).

[Answer]: A

### Q3. FR-5a 운영자 override 플래그 표면
한도(budget/pool/breaker) 우회를 어떻게 노출?
- **A.** 각 주문 tool에 불리언 arg `force`(기본 false). `force=true`면 한도 위반도 통과(단 price-sanity
  · 자동보호는 우회 불가), human-directives 로그에 override 기록. **(권장)**
- **B.** 별도 2단계(먼저 reject+제안 → 운영자가 명시적 override 동사로 재제출).
- **C.** 기타.

[Answer]: A

### Q4. v1에 실제 배선할 order_type / TIF / order_class 범위 (나머지는 explicit reject)
- **A.** order_type = market/limit/stop/stop_limit/**trailing_stop**, TIF = day/gtc/**ioc/fok**,
  class = simple/bracket/oco. **opg/cls(TIF)·oto(class)는 stub-reject**(명시 거부). notional = market+day만. **(권장)**
- **B.** 전부 배선(opg/cls/oto 포함) — Alpaca 완전 패리티, 작업량·테스트 최대.
- **C.** 최소만: market/limit/stop/stop_limit + day/gtc + simple/bracket/oco. trailing_stop·ioc/fok·
  notional·opg/cls·oto 전부 stub-reject(가장 보수적, 후속 트랙에서 확장).

[Answer]: A

### Q5. notional 주문의 리스크 검사 방식
notional은 market+day만 허용(FR-7). budget/pool 검사 시 notional을?
- **A.** 현재가로 qty 환산 후 **기존 position_sizer/budget/pool 로직 그대로 적용**(환산 단가는
  최신가). 일관성↑. **(권장)**
- **B.** notional 금액을 max_position_pct(포트폴리오 대비) 한도와 직접 비교(환산 없이).
- **C.** 기타.

[Answer]: A

---

## 답변 확정 (2026-05-31): Q1=A, Q2=A, Q3=A, Q4=A, Q5=A ("이대로 진행")

## 답변 후 산출물 (Application Design 생성 목록)
- [x] `tracks/F9/application-design/components.md`
- [x] `tracks/F9/application-design/component-methods.md`
- [x] `tracks/F9/application-design/services.md`
- [x] `tracks/F9/application-design/component-dependency.md`
- [x] `tracks/F9/application-design/application-design.md` (통합)
