# Functional Design — KisBroker 도메인 엔티티 매핑 (U1)

> KIS 국내주식 API 응답 ↔ autostock 코어 모델(`src/core/models.py`) 매핑.
> 정확한 KIS 필드명/tr_id는 Code Gen 직전 SDK 검증(이월 항목).

## E-1. Order(autostock) → KIS 주문 파라미터

| autostock Order | KIS 파라미터(예상) | 변환 |
|---|---|---|
| `symbol` | `pdno` | 종목코드 6자리 |
| `side` | 매수/매도 구분 | BUY→매수, SELL→매도 |
| `qty` | `ord_qty` | floor → 정수 문자열 |
| `order_type`/`order_class` | `ord_dvsn` 등 | BR-1 매핑 테이블 |
| `limit_price` | `ord_unpr` | tick 반올림 |
| `stop_price` | `cndt_pric` | tick 반올림(스탑지정가) |
| `take_profit_price`/`stop_loss_price` | (emulated leg 가격) | BRACKET/OCO 분해 |
| `time_in_force` | (당일) | "day"만 허용 |

## E-2. KIS 응답 → FilledOrder

| FilledOrder 필드 | KIS 응답(예상) | 비고 |
|---|---|---|
| `order_id` | `odno`(주문번호) | 취소/조회 키 |
| `symbol` | `pdno` | |
| `side` | 매수/매도 | |
| `qty` | 체결수량(`tot_ccld_qty`) | 부분체결 반영 |
| `filled_price` | 체결평균가(`avg_prvs`/체결단가) | 미체결 시 0 |
| `filled_at` | 체결시각 | 미체결 시 제출시각 |
| `commission` | 수수료 | 미제공 시 0 |

## E-3. KIS 잔고조회 → Position

| Position 필드 | KIS 응답(예상) | 비고 |
|---|---|---|
| `symbol` | `pdno` | |
| `qty` | 보유수량(`hldg_qty`) | 정수 |
| `avg_entry_price` | 매입평균가(`pchs_avg_pric`) | |
| `current_price` | 현재가(`prpr`) | 시세 병합 |

## E-4. KIS 예수금/평가 → PortfolioState

| PortfolioState | KIS 응답(예상) |
|---|---|
| `cash` | 예수금(D+2 정산 예수금/주문가능현금) + 위탁증거금 여유 |
| `equity` | 총평가금액(`tot_evlu_amt`) |
| `positions` | `get_all_positions()` 결과(페이징 합산) |

## E-5. 미체결 → OpenOrder

| OpenOrder | KIS 미체결조회(예상) |
|---|---|
| `order_id` | `odno` |
| `symbol` | `pdno` |
| `side` | 매수/매도 |
| `order_type` | ord_dvsn 역매핑(LIMIT/STOP) |
| `qty` | 미체결잔량(`rmn_qty`) |
| `limit_price`/`stop_price` | `ord_unpr`/`cndt_pric` |

## E-6. 체결내역 → FillEvent (get_fills / ledger)

| FillEvent | KIS 체결내역(예상) | 비고 |
|---|---|---|
| (시각 커서) | 체결시각 | `since` idempotent 커서 |
| symbol/side/qty/price | pdno/구분/체결수량/체결단가 | round-trip 재구성 |

## E-7. 내부 엔티티 — OcoGroup (emulated, **저널 영속** — Critic HIGH-2)

```
OcoGroup:
  group_id: str            # "oco_{n}" (SimulatedBroker 규약 차용)
  symbol: str
  entry_odno: str | None   # BRACKET 진입 주문번호 (OCO-only이면 None)
  tp_odno: str | None      # 지정가 TP resting 주문번호
  sl_odno: str | None      # 스탑지정가 SL resting 주문번호
  qty: int                 # 보호 수량(진입 체결분)
  state: PENDING_ENTRY | ARMED | RESOLVED
```
- **저널 파일(`workspace/kis_oco_groups.json`) write-through**가 권위 출처. 데몬 기동 시 rehydrate 후 거래소
  `get_open_orders`와 대조(체결/취소된 leg 정리, 잔존 leg에 그룹 재바인딩). `OpenOrder`엔 group 정보가 없어
  거래소 조회만으로는 sibling 복원 불가하므로 저널 필수.

## E-8. BaseBroker 신규 속성

| 속성 | KisBroker | Alpaca/Simulated |
|---|---|---|
| `halt_reference_symbol` | `"069500"`(KODEX 200) | `"SPY"`(기본) |
