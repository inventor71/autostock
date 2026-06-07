# R7 — Post-Merge Guide (BrokerApiBroker 동작 수정)

## 무엇이 바뀌나 (prod 브랜치)
**Broker API(sandbox account farm) 경로의 주문 동작 2가지 교정** — 동작 변경(behavior change):

1. **Short-cover 방향 버그 수정(T3-1).** `BUY_TO_COVER`(숏 청산) 주문이 이제 올바르게 **BUY**로
   전송됨. 이전엔 잘못 **SELL**로 나가던 잠재 버그(숏 포지션을 더 키울 수 있던 방향 오류).
   `SELL_SHORT`→SELL은 그대로(Alpaca는 flat 종목 SELL이 숏 오픈).
2. **TIF fail-closed(T3-2).** 미지원 time-in-force(`opg`/`cls`/알 수 없는 값)를 **조용히 DAY로
   강등하지 않고 `BrokerError`로 거부**. `ioc`/`fok`는 이제 정상 지원(이전엔 DAY로 강등). `gtc`/`day`
   및 bracket/OCO 보호레그(GTC)는 동일.

→ Broker API 브로커가 Alpaca Trading API 브로커와 **side/TIF에서 완전히 동일하게** 동작.

## 영향 범위
- **Broker API 경로(`broker.provider: broker_api`, sandbox account farm)에만** 영향.
  기본 Alpaca Trading API 경로·KIS 경로는 무변경.
- 숏 트레이딩은 마스터 토글 `shorting_enabled`(기본 OFF, F60) 뒤에 있어, 그 기능을 쓰지 않으면
  T3-1은 실사용상 비활성. 켜서 Broker API farm에서 숏을 돌리는 경우 이 수정이 중요.

## 전제조건
- 없음. 코드 변경만(설정/env 키 추가 없음). 데몬 재시작으로 반영.

## 실사용 검증 체크리스트
1. Broker API 경로 사용 시: `ioc`/`fok` TIF 주문이 거부되지 않고 통과하는지, `opg` 등은
   `BrokerError`로 막히는지 로그 확인.
2. 숏 운용 시: `BUY_TO_COVER`가 브로커에 **BUY**로 접수되는지(체결 방향) 확인.
3. 회귀: 일반 BUY/SELL/day/gtc 주문이 이전과 동일하게 동작하는지.

## 롤백
- `refactor/R7` revert → 두 override가 복원되어 이전(버그 포함) 동작으로 되돌아감.

## 한계 / 범위 밖
- **T3-3 제외**: extended_hours/client_order_id/trailing-stop 패리티는 미포함(SDK 수용 여부 미확인).
  필요 시 별도 트랙. Broker API는 현재 `_extras→{}`(base 기본)으로 해당 필드 미전송.

## 검증
- `tests/test_broker_api_broker.py` 44 passed(교정 동작 명시), 브로커/실행 회귀 190 passed,
  전체 1073 passed. 실계정 페이퍼 스모크(특히 BUY_TO_COVER 방향)는 Broker API farm 계정에서
  운영자가 1회 확인 권장(fake로는 외부 접수 방향을 증명 불가).
