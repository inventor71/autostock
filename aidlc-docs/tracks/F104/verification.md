# F104 검증 / 운영

## 원인

RiskManager는 Alpaca 소수점 수량을 위해 부분 매도를 9자리까지 계산하지만, Toss는 6자리만
받는다. F103의 정수 잔고 중심 테스트가 이 경계를 놓쳤다. F103의 idle 후속 처리에서 같은
예외를 매 poll마다 재시도해 로그가 누적됐다. 모델 호출 자체는 정상 완료됐으며, 두 dry에서
GOOGL 부분 매도와 Opus SNDK 부분 매도가 제출 전에 거부됐다.

## 변경

- Toss simple MARKET SELL을 제출할 때 Decimal/ROUND_DOWN으로 0.000001주 단위에 맞춘다.
  의도보다 많은 수량을 보내지 않는다. 수량을 order에도 반영해 실행 로그와 제출값이 일치한다.
  최소 단위 미만은 거부하며 기존 BUY/limit/protection 제약과 live 읽기 전용 경계는 유지한다.
- shadow 오류별 retry 상태를 장부에 저장한다. 30/60/120/240/300초 간격으로 재시도하며
  재시작에도 유지한다. 새 지시·만료·완료는 기존 retry에서 벗어난다. 부분 체결 대기는
  error backoff를 적용하지 않아 체결 후 보호는 바로 진행한다.
- report와 account 도구의 execution_retries로 실패/시도 횟수/다음 시각을 공개한다.
  feed health나 모델 complete만으로 모든 결정이 실행됐다고 판단하지 않는다.

## 검증

기존 main venv/Python 3.12, F104 worktree에서 실행:

```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q tests/toss/test_broker.py tests/toss/test_shadow.py tests/test_executor.py
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q
/home/jihoonpark/Project/autostock/venv/bin/ruff check src/evals/toss_shadow.py src/execution/brokers/toss/broker.py src/execution/brokers/toss/shadow.py tests/toss/test_broker.py tests/toss/test_shadow.py
git diff --check
```

관련 **110 passed**, 최종 전체 **1,834 passed**, 기존 경고 30개, 53.66초.
Toss/runner 변경 파일 Ruff 및 diff 검증 통과. 새 회귀 10개:

- 실제 실패 패턴 105.005567주의 30%/40%, 76.005632주의 60%와 전량 매도, 극소량 부분 매도.
- 부분 체결마다 executor를 다시 생성해도 중복 없이 체결하고 실제 남은 수량만 보호한다.
- 최소 단위 미만 네트워크 전 거부와 live 어댑터 mock 전송값/실행 로그 수량 일치.
- 실패 간격의 재시작 보존, 두 번째 실패의 간격 증가, 복구 후 보호 즉시 실행.
- 새 지시와 만료 지시의 backoff 우회/기록 정리.

테스트는 mock HTTP/가상 장부만 사용했으며 실제 주문이나 유료 모델 호출이 없다.
외부 API의 실제 소수점 매도 접수까지 시험한 것은 아니다.

## 적용 후 확인

기존 설정을 유지하고 두 tmux의 dry 프로세스를 재시작한다. 먼저 private 백업을
research-comparisons/F104/에 저장한다. 기존 결정 커서·과거 체결을 되감지 않는다.
오류로 지연됐던 유효한 결정은 새 호가에서 제출하며 과거 가격으로 소급 체결하지 않는다.
장부 runtime_revisions에 F104 적용 경계를 남긴다. 오류 발생 구간은 모델 간 수익 비교 시
운영 장애로 구분해야 한다.

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 report
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-fable-20261124 report
```

두 run/report 창이 살아 있고, 실행 커서가 진전하며, execution_retries에 같은 정밀도 오류가
생기지 않는지 확인한다. orders/fills의 새 수량은 6자리 이내이고 후속 보호는 잔여 수량과
일치해야 한다. 별도 설정 키는 없으며 30초~5분 간격이 기본이다. 일반 콘솔은 건드리지 않는다.
코드 동작 불변이어도 다음 일반 콘솔 attach 시 F43에 의한 1회 자동 재시작은 정상이다.
문제 시 해당 tmux run 창의 Ctrl-C로 dry만 중단하고 `git revert -m 1 <F104-merge-sha>`로
코드를 복구한다. 백업 복원은 이후 가상 체결을 제거하므로 현재 장부를 별도 보관해야 한다.
