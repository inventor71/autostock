# F101 — 기존 Toss 연결 사용

이미 실행한 연결 명령:

```bash
venv/bin/python -m src.execution.brokers.toss.setup --from-toss-stock ~/Project/toss-stock
```

공유 토큰 파일 경로와 계좌 선택만 `~/.config/autostock/toss/credentials.json`에 저장했다.
이 파일은 Git 밖에 있으며 권한은 0600이다. 연결 과정에서 키를 읽거나 새 토큰을
발급하지 않았다. 기존 toss-stock 모니터링이 토큰 갱신을 맡는다.

연결 상태 확인:

```bash
venv/bin/python -m src.execution.brokers.toss.setup --check
```

Toss 계좌를 조회하는 일회성 실행:

```bash
AUTOSTOCK_BROKER_PROVIDER=toss AUTOSTOCK_BROKER_PAPER=false \
  venv/bin/python -m src.agent.tools account
AUTOSTOCK_DATA_PROVIDER=toss venv/bin/python -m src.agent.tools quote AAPL
```

공유 연결은 읽기 전용으로 고정되어 있다. 데몬의 기본 broker를 바꾸지 않는다.
토큰 만료/폐기 오류가 나면 toss-stock 모니터링이 연결을 갱신한 뒤 `--check`를 재실행한다.
연결만 해제하려면 Autostock의 위 연결 파일을 제거한다. 원본 키/토큰 파일은 유지한다.

검증: `venv/bin/python -m pytest tests/toss -q` (99 passed), 전체 `tests -q` (1,770 passed).
실계좌의 GET 조회와 US 시세/완성 일봉까지 확인했고 주문 API는 호출하지 않았다.
