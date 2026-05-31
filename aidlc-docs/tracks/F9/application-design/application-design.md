# F9 — Application Design (통합)

> 운영자 콘솔 주문 입력 계약을 슬래시 문자열 → **구조화 Alpaca형 MCP tool call**로 교체하되 데몬
> RiskManager→Broker 게이트는 유지(휴먼 경로엔 게이트를 **신규 도입**). 결정: Q1=A, Q2=A, Q3=A,
> Q4=A, Q5=A. 상세 문서: [components](components.md) · [component-methods](component-methods.md) ·
> [services](services.md) · [component-dependency](component-dependency.md).

## 1. 설계 요지
- **콘솔(C1)**: 단일 `steer` → 6개 구조화 주문 tool(`place_stock_order`/`cancel_order_by_id`/
  `cancel_all_orders`/`replace_order_by_id`/`close_position`/`close_all_positions`), 각자 zod 스키마
  + opencode `ask` 컨펌. 안전/lifecycle/approval/context 동사는 결정적 경로 유지(parser 트림).
- **계약(C2)**: verb 집합 확장(+place_order/replace_order/cancel_all/close_position/close_all) +
  **per-verb 주문 args 스키마** 고정(parser 주문문법 제거 전 선행, NFR-3).
- **데몬 핸들러(C3)**: 신규 `_v_*` 핸들러가 args→Order→게이트→브로커. buy/sell shorthand도 동일
  게이트 합류. 안전동사 결정적 디스패치 보존.
- **Order(C4)**: `OrderType`+TRAILING_STOP, `OrderClass`+OTO, `notional`/`extended_hours`/
  `client_order_id`/`trail_price`/`trail_percent` + validator.
- **리스크 게이트(C5)**: 신규 `receive_human_order(order, *, force)` — 휴먼 주문에 budget/pool/
  breaker 검사(현재 무게이트 정정) + clamp/제안 + 자동보호 + price-sanity. `force`는 한도만 우회.
  `evaluate_signal`(에이전트) 무변경.
- **브로커(C6)**: trailing/notional/extended_hours 매핑, 미지원 TIF explicit reject(무음 DAY 강등
  제거), 신규 replace/cancel_all/close_all(단순 주문만 replace).

## 2. 핵심 결정 (critic + 사용자)
1. **휴먼 경로 게이트는 신규**(FR-5): 현재 `build_human_buy`는 한도/브레이커 미적용. C5가 이를 처음
   도입. 운영자는 `force`로 한도만 우회 가능(price-sanity·자동보호는 불가).
2. **하이브리드 동사**(FR-2): 주문만 구조화 tool, kill/halt/flatten 등 안전동사는 결정적 유지.
3. **replace 보수적**(Q2=A): bracket/oco leg 주문 replace는 v1에서 reject.
4. **v1 배선**(Q4=A): trailing_stop+ioc/fok까지 배선, opg/cls/oto는 stub-reject.
5. **계약 강화**(NFR-3): per-verb args를 양 언어에 고정.

## 3. 불변/안전 (블로킹 확장 — inline 강제)
- **NFR-1 advisor-only(defense-in-depth)**: 주문 tool은 콘솔 MCP에만. 에이전트 = MCP 미구성 + 토큰
  스크럽 + deny-hook + 데몬 토큰 체크. F9 신규 도달면 없음.
- **SECURITY-03**: 토큰 로그/결과/이벤트 비노출(redacted 유지).
- **SECURITY-13/NFR-2**: zod(콘솔) + pydantic per-verb(데몬) 이중 safe-deserialize.
- **SECURITY-15/NFR-4 fail-closed**: 토큰 없음/미배선 TIF·class/검증 실패/한도 위반(비-force) →
  주문 없음. 데몬 게이트가 최종 권위.

## 4. 빌드 순서 / 유닛
U-RISK(C4→C6→C5) → U-DAEMON(C3+C2 py) → U-CONSOLE(C1+C2 ts, parser 트림). 교차언어 계약 테스트는
U-CONSOLE 완료 시 green. (execution-plan.md §4와 일치)

## 5. Functional Design으로 미룬 상세
- C5 clamp/제안 수식, notional 환산 경계, 자동보호 레벨 해석, price-sanity 임계.
- C6 replace의 단순-주문 판별 + 부분취소 레이스 처리.
- per-verb args 검증 에러 → 구조화 reason_code 매핑 표.
