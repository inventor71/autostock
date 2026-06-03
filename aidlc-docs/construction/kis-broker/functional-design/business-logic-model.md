# Functional Design — KisBroker 비즈니스 로직 모델 (U1)

> 기술 비종속 로직. 코드 경로/엔드포인트 검증은 Code Gen 직전. Option B(emulated bracket/OCO) 기반.
> 참조: `src/execution/base.py`(BaseBroker), `src/core/models.py`(Order/FilledOrder/…),
> `src/execution/brokers/simulated.py`(OCO group 의미 — 폴링 버전으로 재현).

## 1. 주문 제출 흐름 (submit_order)

```
Order ──▶ [정규화] ──▶ [order_class 분기] ──▶ KIS API ──▶ FilledOrder
          │              ├─ SIMPLE/MARKET → 시장가(ORD_DVSN=01)
          │              ├─ SIMPLE/LIMIT  → 지정가(ORD_DVSN=00, tick 반올림)
          │              ├─ STOP          → 스탑지정가(cndt_pric, tick 반올림)
          │              ├─ BRACKET       → 진입 1건 + (체결확인) + TP/SL resting 2건, OCO 그룹
          │              └─ OCO           → TP/SL resting 2건, OCO 그룹 (진입 없음, 보유분 대상)
          └─ [정규화]: 심볼→pdno, qty→정수(floor), 가격→tick 반올림, side→매수/매도 코드
```

### 정규화 단계 (모든 주문 공통, 분기 전)
1. **심볼 매핑**: autostock symbol → KIS `pdno`(종목코드 6자리). KR은 통상 동일(005930 등).
2. **수량 정수화**: `qty_int = floor(qty)` (FD-3/Q3=A). `qty_int < 1`이면 `BrokerError`(주문 거부, fail-closed).
3. **가격 tick 반올림**: 지정가/스탑지정가 한정, `round_to_tick(price)` 최근접(FD-2/Q2=A).
4. **side 매핑**: BUY→매수, SELL→매도 (KIS 주문 API의 매수/매도 구분).

### 분기별 처리
- **MARKET**: `ORD_DVSN=01`, 가격 0(또는 미지정). 국내주식 모의투자 포함 지원.
- **LIMIT**: `ORD_DVSN=00`, `ord_unpr=round_to_tick(limit_price)`.
- **STOP(스탑지정가)**: 조건부지정가/스탑지정가 경로, `cndt_pric=round_to_tick(stop_price)`,
  체결 시 가격은 지정가. (단일 resting 보호주문 — 거래소측.)
- **BRACKET / OCO**: §3 emulated 상태기계.

### 체결 확인
- 시장가/지정가 제출 후 주문번호(`odno`) 수신 → `get_order_status(odno)` 폴링으로 체결 수량/평균가 확정.
- 즉시 체결(시장가)·부분 체결·미체결을 구분. `FilledOrder`는 **확정 체결분**으로 구성(미체결 시 filled_qty=0).

## 2. 토큰 수명 관리 (FD-5/Q5=A — Lazy)

```
[API 호출 직전] → token_age = now - token_issued_at
                  ├─ token_age > 23h  → 재인증(auth) → token_issued_at = now
                  └─ else             → 기존 토큰 사용
```
- 추가 스레드 없음. `_ensure_token()`를 모든 KIS 호출 wrapper 진입점에서 호출.
- 재인증 실패 시 `BrokerError`(fail-closed) — 만료 토큰으로 호출 강행 금지.
- 토큰/시크릿은 로그에 절대 미출력(SECURITY-03/12).

## 3. emulated bracket/OCO 상태기계 (Option B 핵심)

> SimulatedBroker의 OCO group 의미(`group` id, 한쪽 leg 체결 시 형제 leg 취소 —
> `simulated.py:_cancel_group`)를 **거래소 resting order + 폴링**으로 재현.

### 상태
```
오더그룹(OcoGroup): { group_id, symbol, entry_odno?, tp_odno, sl_odno, qty, state }
state ∈ { PENDING_ENTRY, ARMED, RESOLVED }
```

### 전이
```
BRACKET 제출:
  1) 진입 주문(시장가/지정가) 제출 → PENDING_ENTRY
  2) [Q4=A] 진입 직후 동기 폴링(짧은 타임아웃)으로 체결 확인
       ├─ 체결됨(qty_f) → TP(지정가)·SL(스탑지정가) resting 2건 arm(qty=qty_f) → ARMED
       └─ 미체결/부분 → 다음 reconcile 턴에서 체결분만큼 arm (PENDING_ENTRY 유지)
OCO 제출(보유분 보호):
  - 진입 없음. 보유 수량 대상 TP·SL resting 2건 arm → ARMED

reconcile_oco() [전용 always-on seconds job — Critic HIGH-1 정정]:
  for g in ARMED groups:
    - get_open_orders / get_order_status로 tp_odno·sl_odno 상태 확인
    - 한쪽 체결 감지 → 다른 쪽 cancel_order → RESOLVED
    - 양쪽 미체결 → 유지
  for g in PENDING_ENTRY groups:
    - 진입 체결 확인되면 잔여 수량 arm → ARMED
```

### reconcile 실행 위치 (Critic HIGH-1 정정)
- ⚠️ 기존 5초 seconds-job들(`agent.py:313`)은 **전부 steering-gated** → standalone KIS(steering 없음)엔
  초단위 job이 **없음**. 따라서 "기존 5초 job 합승"은 **무효**.
- 해결: **steering 무관 always-on** `add_seconds_job(kis_reconcile, N, "kis_reconcile")`를 KIS 경로에서 신규 등록
  (reconcile_oco + held∪open 가격피드). steering 유무와 독립.

### 영속화 (Critic HIGH-2 정정 — 사용자 결정: 저널 파일)
- OcoGroup은 in-memory + **저널 파일(`workspace/kis_oco_groups.json`) write-through**.
- 데몬 기동 시 rehydrate → 거래소 `get_open_orders`와 대조해 잔존 leg에 그룹 재바인딩, stale 그룹 정리.
- `OpenOrder` 모델엔 group 정보가 없으므로(레이스/재시작), 저널이 **권위 출처**; 거래소 조회는 검증용.

### 보호 계층 (defense-in-depth — risk-execution-redesign 부합)
1. **(주) 거래소 resting 스탑지정가(SL)** — 폴링 없이도 가격 도달 시 체결.
2. **(백업) polled exit** — `run_polled_exits`(executor.py:317) + reconcile_oco.
- ⚠️ 단, `protected_symbols()`는 **STOP leg 존재** 기준으로 판정해야 함(Critic MED-3): TP만 남고 SL이
  거부/취소된 경우 "보호됨"으로 오판해 백업이 스킵되는 구멍 차단. SL arm 실패 시 그룹 전체 실패(TP 취소).

### oversell 안전 (범위 한정)
- 현금계좌: 남은 SELL leg가 취소 전 체결돼도 보유 초과분은 KIS가 거부 → **주문 거부**는 안전.
- ⚠️ 단 이는 *계좌 안전*이지 *보호 커버리지 안전*이 아님 — SL leg가 거부되면 보호가 사라지므로 위 MED-3 처리 필수.

## 4. 장 시간 / 스케줄 (is_market_open) — FD-6

- **KST 정규장**: 09:00–15:30, Mon–Fri. (장 마감 동시호가 15:20–15:30 포함 범위.)
- `is_market_open()`: `Asia/Seoul` 현재시각 기준 계산. 오류 시 **False**(fail-closed, SECURITY-15).
- 휴장일(공휴일): PoC는 평일+시간만 1차 판정. (정확 휴장일 캘린더는 후속 — 거래 시도 시 KIS 거부가 2차 방어.)
- 스케줄(서비스 orchestration): 연구 08:00 / 개장 09:00 / 마감 전 15:20 KST (`TradingScheduler` timezone 파라미터화).

## 5. standalone 가격 피드 (FD-8/Q7=A)

- steering 미사용 시에도 도는 최소 job(5초): **보유 포지션 ∪ open order 심볼만** `get_latest_prices` + `reconcile_oco`.
- universe 전체(≈350) 폴링 안 함 → rate-limit 절약. (모니터링 풍부함은 보호 목적 아님.)

## 6. rate limit / HTTP

- 초당 호출 상한(실전 ~20, 모의 더 낮음) 준수 — 토큰버킷/최소 간격. 초과 시 backoff(재시도) 후 실패 시 fail-closed.
- HTTP connect/read timeout 적용(F14 패턴) — 무한 대기 금지.

## 7. close_position (FD-9/Q8=A)

- 보유 수량 확인 → **시장가(ORD_DVSN=01) 매도**. 확실한 청산 우선(슬리피지 감수).
- 보유 0이면 None. 관련 OCO 그룹 있으면 함께 cancel.
