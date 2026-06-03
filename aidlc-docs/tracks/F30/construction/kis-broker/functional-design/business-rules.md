# Functional Design — KisBroker 비즈니스 규칙 (U1)

> 결정적 규칙·검증·제약. PBT 대상은 §PBT 참조.

## BR-1. 주문유형 매핑 (결정 테이블)

| autostock | order_type / order_class | KIS 파라미터 | 비고 |
|---|---|---|---|
| 시장가 | MARKET / SIMPLE | `ORD_DVSN=01`, 가격 0 | 국내주식 모의 포함 지원 |
| 지정가 | LIMIT / SIMPLE | `ORD_DVSN=00`, `ord_unpr=tick(p)` | tick 반올림 필수 |
| 스탑지정가 | STOP | **실전만**: ORD_DVSN=22 + `cndt_pric=tick(stop)` (raw `kis.fetch`). **모의: 미지원**(폴링 대체) | BR-1a |
| 브라켓 | BRACKET | 진입 1 + TP(지정가 resting) + SL(실전=스탑22 resting / 모의=폴링), OCO 그룹 | §emulated, BR-1a |
| OCO | OCO | TP(지정가 resting) + SL(실전=스탑22 / 모의=폴링), OCO 그룹 | 보유분 보호, 진입 없음 |
| 매수/매도 | side BUY/SELL | KIS 매수/매도 구분 코드 | |
| TIF | time_in_force="day" | 일반 주문(당일) | KIS GTC 미지원 → day 고정, day 외 값은 거부 |

- **TRAILING_STOP**: KIS 네이티브 미지원 → `BrokerError`("KIS: trailing_stop 미지원"). (Order 모델엔 존재하나 KIS 경로 거부.)

## BR-1a. 보호 모델 — 환경(모의/실전)별 분기 (2026-06-03 실증 확정)
> 검증: KIS **모의투자는 스탑지정가(ORD_DVSN=22) 미지원**(`40970000 "모의투자에서 제공하지 않는 주문유형입니다"`).
> 실전은 지원. 따라서 KisBroker는 `self.paper`로 SL 보호 메커니즘을 분기한다. ([[kis-api-facts]])

- **공통**: 진입 = 시장가/지정가. **TP(익절) = 거래소 resting 지정가 매도**(모의·실전 모두 지원, gap-up 자동체결).
- **SL(손절)**:
  - **모의(`paper=True`)**: 거래소 스탑 불가 → **폴링 SL**. SL leg를 거래소에 걸지 않고 OcoGroup에 stop level만 보유 →
    `run_polled_exits`가 가격 감시 후 시장가 매도. `protected_symbols()`가 STOP-leg 기준(BR-5a)이라
    TP만 resting인 KIS 심볼은 자동으로 폴링 백업 대상이 됨(MED-3 수정과 정합).
  - **실전(`paper=False`)**: **거래소 resting 스탑지정가**(ORD_DVSN=22 + cndt_pric, raw `kis.fetch`) → defense-in-depth 복원.
- **reconcile_oco**: 두 환경 모두 필요 — 한쪽(폴링 SL 체결 또는 거래소 leg 체결) 발생 시 다른 쪽 정리(TP/SL cancel).
- `supports_stop_orders` 속성: `not self.paper` (모의 False, 실전 True). submit_order가 이걸로 SL 경로 선택.

## BR-2. 호가단위(tick) 반올림 — Q2=A 최근접

가격대별 tick (2023 KRX 호가단위 단일화; KOSPI=KOSDAQ 동일):

| 가격 구간(원) | tick |
|---|---|
| ~ 2,000 미만 | 1 |
| 2,000 ~ 5,000 미만 | 5 |
| 5,000 ~ 20,000 미만 | 10 |
| 20,000 ~ 50,000 미만 | 50 |
| 50,000 ~ 200,000 미만 | 100 |
| 200,000 ~ 500,000 미만 | 500 |
| 500,000 이상 | 1,000 |

- `round_to_tick(p)` = 입력 구간 tick으로 최근접 반올림 후, **결과가 다른 tier로 넘어가면 출력 tier 기준 재snap**
  하여 고정점 보장(Critic LOW-6). 즉 출력값은 자신이 속한 tier의 tick 배수.
- 적용 대상: LIMIT `ord_unpr`, STOP `cndt_pric`, emulated TP/SL leg 가격. (시장가는 미적용.)
- 경계: "이상~미만" — 정확히 경계값이면 상위 구간 tick 적용(예: 2,000 → 5원 tick).
- 불변식(PBT): 멱등(`f(f(p))=f(p)`), **출력 tier tick의 배수**, 단조 비감소. (입력 tier가 아니라 출력 tier 기준 — 경계 교차 케이스 flake 방지.)

## BR-3. 정수 수량 — Q3=A

- BUY / 부분 SELL: `qty_int = floor(qty)`.
- **전량 청산(close_position)**: 보유 수량 그대로(floor 무관 — 보유는 이미 정수).
- emulated TP/SL resting leg 수량 = **진입 체결 수량**(qty_f). 부분 체결이면 체결분만 arm.
- `qty_int < 1` → `BrokerError`(주문 거부). 음수/0 거부.

## BR-4. 토큰 — Q5=A Lazy

- 매 KIS 호출 전 `_ensure_token()`: `age>23h`이면 재발급. 재발급 실패 → `BrokerError`(fail-closed).
- 토큰/시크릿/계좌번호 일부 마스킹, **로그 미출력**(SECURITY-03, SECURITY-12).

## BR-5. emulated OCO reconcile — Q1=A, Q4=A (Critic HIGH-1/HIGH-2 정정)
- reconcile 주기: **steering 무관 전용 always-on seconds job**(`kis_reconcile`)에서 실행. 기존 5초 job들은
  steering-gated라 standalone에선 안 돎 → "합승" 폐기. 최대 지연 ≤ job 주기.
- **영속화**: OcoGroup을 저널 파일(`workspace/kis_oco_groups.json`) write-through, 기동 시 rehydrate + 거래소
  `get_open_orders` 대조. (재시작 후 sibling 복원 — 사용자 결정.)
- 진입 체결 확인: 진입 직후 **동기 폴링**(짧은 타임아웃). 체결 시 즉시 TP/SL arm; 미체결/부분이면 다음 턴.
- 한쪽 leg 체결 감지 → 다른 쪽 즉시 `cancel_order` → 그룹 RESOLVED → 저널 갱신.
- reconcile 중 API 오류 → 그룹 상태 보존(다음 턴 재시도), 거래소 resting 보호는 유지(fail-safe).

## BR-5a. 보호 커버리지 (Critic MED-3)
- `protected_symbols()`는 "open order 존재"가 아니라 **STOP 종류 leg 존재** 기준으로 판정
  (executor.py:302 공유 — Alpaca 원자 OCO도 STOP leg 보유라 안전).
- emulated arm 시 SL leg 거부/실패 → **그룹 전체 실패 처리(TP 취소)** → polled 백업이 해당 심볼 재engage.
- ⇒ "TP만 남아 보호된 것처럼 보이는" 하방 무방비 구멍 차단.

## BR-5b. 취소-정산 대기 (Critic MED-5)
- `_cancel_and_wait`의 timeout/interval은 **broker 속성**으로 노출(예 `cancel_settle_wait`). KIS 취소가 동기면
  0/짧게(KIS 2/s 스로틀 하 6초 폴링 stall 방지). Alpaca는 기존 6초 유지.

## BR-6. 장 시간 / fail-closed — Q (FD-6)

- `is_market_open()`: KST 09:00–15:30 Mon–Fri. 계산 오류 시 **False**.
- 장외 주문 시도: 1차 `is_market_open()` 차단, 2차 KIS 거부 → `BrokerError`로 매핑.

## BR-7. 청산 — Q8=A

- `close_position`: 보유분 **시장가 매도**. 보유 0 → None. 연계 OCO 그룹 cancel.

## BR-8. 잔고/페이징

- 모의투자 잔고조회 응답 20종목/회 → 연속조회(`get_all_positions` 페이징)로 전체 수집.
- `get_portfolio_state`: cash=예수금(+위탁증거금 여유), equity=총평가금액, positions=get_all_positions().

## BR-9. 에러 매핑 (fail-closed, SECURITY-09/15)

| 상황 | 처리 |
|---|---|
| 토큰 발급/갱신 실패 | `BrokerError`, 호출 중단 |
| rate-limit 초과 | backoff 재시도 → 지속 실패 시 `BrokerError` |
| HTTP timeout | `BrokerError`(무한대기 금지) |
| KIS 거부(주문/장외/수량) | 메시지 매핑한 `BrokerError` |
| 미지원 주문유형(TRAILING_STOP) | `BrokerError` |
| 부분 체결 | `FilledOrder`는 체결분만, 잔여는 미체결로 추적 |

## PBT 대상 (PBT Partial — PBT-02/03/07/08)
- `round_to_tick`: 멱등·tick 배수·단조(PBT-03 invariant).
- 수량 floor: `qty_int ≤ qty`, `qty_int ≥ 1` 보장 또는 거부(PBT-03).
- 주문유형 매핑 round-trip: Order → KIS 파라미터 → (역매핑 가능 필드) 일관성(PBT-02).
- generator: 현실적 가격(1~1,000,000원)·수량 분포(PBT-07), 실패 케이스 shrink 재현(PBT-08).
