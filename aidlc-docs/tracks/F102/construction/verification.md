# 검증과 리뷰

## 테스트

```bash
venv/bin/python -m pytest tests/toss -q
venv/bin/python -m pytest -q
venv/bin/python -m ruff check src/execution/brokers/toss src/execution/brokers/factory.py src/evals/toss_shadow.py tests/toss/test_costs.py tests/toss/test_shadow.py
git diff --check
```

최종 전체 suite: **1806 passed, 30 기존 경고**, 39.69초. 새 회귀 테스트 36개 포함.
Toss 전체 135개는 이 전체 suite 안에서 통과했다. 새 비용/가상 브로커/runner 및
관련 테스트 Ruff 통과, `git diff --check` 통과.

## 검증하는 성질

- KST 만료 자정, 6시간 TTL, 무기한 sentinel, 실패 시 이전/0 요율 금지, 계좌별 캐시.
- 요청 도중 만료되는 요율과 호가 조회 도중 시장 마감 처리.
- 실제 ask/bid를 사용하는 지연 체결, stale/crossed/null 호가 차단, 잔량 제한과 부분 체결.
- 같은 호가를 재시작으로 재소비하지 않음. 수수료 변동이 이전 부분 체결을 재평가하지 않음.
- 매수 현금 예약/잔고 불변식, 매도 SEC 비용, OCO peer 취소, 갭 손절, DAY 만료.
- 같은 초기 buy-and-hold 대비 spread/fee 손실 산출, 새 실험 초기화 중복 금지.
- 에이전트→RiskManager→주문→호가 체결의 통합, 커서 저장 전 중단 복구.
- 모델 실행 중 호가 관찰 지속, 실패/중단 모델의 부분 결정 rollback, 재시작 후 호출 한도 유지.
- factory/CLI/독립 workspace가 가상 계좌를 선택하며 기존 live agent 모드로 우회하지 않음.
- GET-only 실제 smoke, 개인 파일 권한, 원격 주문/Alpaca 계좌 조작/모델 호출 없음.

## 리뷰에서 수정한 사항

1. provider 필드가 없는 기존 KIS 설정 테스트 4개 회귀 → 안전한 getattr 분기 복구.
2. 부분 체결 중 요율 변경 → 기존 notional 전체를 새 요율로 재계산하지 않고 누적 원가 분리.
3. 모델 오류의 부분 journal이 다음 턴에 실행될 위험 → 턴 backup과 started/executing 복구 분리.
4. 호가 수집 중 요율 만료/정규장 종료 → 체결 직전 다시 검증.
5. 마감 경계 테스트의 시계 fixture가 현재 초를 보존하던 문제 → 거래소 세션 시간을
   정각으로 고정한 뒤 해당 테스트와 전체 suite 재실행 통과.

기능 검증과 수익 검증을 구별한다. 실제 여러 날의 에이전트 실험은 아직 실행하지 않았으며,
실주문 체결/취소 지연이나 수익 개선을 입증하지 않는다. 모델의 재량 판단은 기존 prompt와
RiskManager에 맡기고, 짧은 비용·가상 계좌 문맥만 추가했다.
