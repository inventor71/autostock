# 검증과 리뷰

## 실행과 결과

Python 3.12와 기존 main venv를 사용했다. 의존성 변경은 없다. worktree에서:

```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q tests/test_executor.py tests/toss/test_shadow.py tests/toss/test_quality.py
git diff --check
```

- 최종 전체 suite: **1,824 passed**, 30개 기존 경고, 44.63초.
- 관련 suite: **70 passed**, 8.70초. 총 회귀 테스트 증분은 18개다.
- 변경 Python 파일 Ruff: 기존 32개 진단과 비교하여 **신규 진단 0개**.
  기존 광범위 exception 처리/스타일 경고는 범위를 벗어나므로 유지했다.
- `git diff --check` 통과. 외부 주문·유료 모델 호출 없이 mock HTTP와 로컬 장부로 검증했다.

## 실제 실패 패턴과 경계 검증

- 10주에서 `SELL 50% → HOLD(stop, target)` 입력: 기존 executor는 HOLD만 처리해
  10주를 유지했다. 수정본은 SELL/HOLD를 모두 처리하고 남은 5주만 보호한다.
- 부분 체결 중 기존 보호 수량 축소, 재시작, 새 HOLD로의 교체에서도 매도 의존성을 유지한다.
  체결 종료 전 보호 재조정이 미체결 매도를 취소하지 않으며, 중복 매도가 없다.
- 실패한 매도 후 보호 보류, 전량 매도 후 허위 포지션 생성 방지, 수량이 다른 기존 보호 재조정.
- 이미 지난 목표가의 대체 주문은 기존 정상 보호를 취소하기 전에 거부한다.
  stop-only 보호의 세션 간 유지와 실제 stop/exit 체결 이유를 account 도구에서 확인한다.
- 모델 호출 한도가 끝나도 idle runner가 체결 후 보호를 마무리한다.
  poll 도중 종료 기한을 넘으면 주문/모델 호출을 진행하지 않는다.
- 재조회가 실제 새 source timestamp를 얻은 경우에만 체결을 복구한다.
  stale 소액 잔고는 indicative 평가만 가능하며 15초 체결 제한은 그대로 적용한다.
- 현금 포함 strategy/hold 각각의 합산 1% 경계, 120초·미래·timestamp 누락·오류 경계.
  평가 불가능 시 신규 BUY와 모델 턴을 보류한다.
- 장중 비교 수익의 시작점은 첫 완전 신선한 관측이다. 시드 재평가 수익과 구분한다.

## 과거 자료의 오프라인 검토

기존 667개 스냅샷을 읽기만 하고 새 품질 기준으로 분류했다:
309개 fresh, 344개 indicative, 14개 unavailable. 엄격한 신선도 46.33%는 변하지 않는다.
평가 허용 범위에 드는 비율 97.90%는 **재분류 결과**이며 호가가 실제 빨라진 결과가 아니다.
재조회로 얻을 장중 개선 폭은 새 세션에서 관측해야 한다.

원본 장부·결정·체결·커서는 수정하지 않았다. 상세 비교는 gitignored private 디렉터리
`research-comparisons/F103/offline-review.json`에 보관한다. 이 검증은 의도 보존과 데이터
품질 판별을 입증하며, 수익 증가 또는 모델 우월성을 입증하지 않는다.

## 리뷰에서 보완한 사항

보호 지시의 index에 의존성을 묶으면 새 HOLD가 대체할 때 유실될 수 있어, 종목별 미체결
노출 주문 ID를 저장하도록 수정했다. 재조회 오류가 이전 성공 book을 체결 가능하게 만들지
않도록 오류 종목을 제외했다. 가격만 같은 보호 주문도 잔여 수량이 다르면 재조정한다.
모델이 청산 이유를 추측하지 않도록 최근 실제 가상 체결 10개와 stop/take-profit/exit 구분을
계좌 도구에 제공한다. 프롬프트에는 이 계약만 간결히 추가했다.
poll 중 새 주문이 들어오는 경우도 최종 품질 기준으로 strict snapshot을 판정하며,
실험 종료 시 agent_ready=false가 되도록 보고 상태를 맞췄다.

Security baseline/PBT extension은 F102와 동일하게 Disabled. 이 변경의 수량·현금·재시작
회귀 검증은 일반 테스트 범위에 포함했다. 원격 push나 실계좌 주문은 수행하지 않는다.
