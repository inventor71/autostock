# F102 사용 안내

## 변경 사항

Toss 계좌 수수료를 적용 종료일(KST)과 최대 6시간 간격으로 재확인한다.
만료 후 재조회 실패 시 이전 요율을 연장하지 않는다. 연간 양도소득세는 제외한다.
별도 가상 계좌로 에이전트 판단을 실제 Toss 호가와 연결해 관찰할 수 있다.

## 활성 조건과 실행

기존 Toss 연결을 그대로 사용한다. `toss-stock`의 토큰 갱신 모니터는 계속 켜 둔다.
기존 Alpaca 데몬과 설정은 전환하지 않는다. 다음은 새 실험을 시작하는 명령이다.

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 init --days 7
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 run --agent
```

두 번째 명령은 실제 설정된 모델을 호출한다. 기본 하루 8회/60분 간격/7달력일이며,
실제 주문은 하지 않는다. 시작 시점 모델·위험 설정·거래 가능 종목을 저장한다.
같은 디렉터리를 다시 초기화하지 말고 `run --agent`로 재개한다.
서로 다른 가정/모델의 비교는 새 디렉터리를 만든다.
자동 실행은 [Toss 문서](../../../docs/TOSS.md)의 별도 systemd 서비스 예시를 참고한다.

관찰만 한 번 실행하려면 `run --once`, 결과는 다음 명령으로 확인한다.

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 report
```

정상 확인: `simulation: true`, 예상한 `agent_config`/`runner`, `health.status`,
`fill_count`, `fees_usd`, `excess_return_pct_points`, `metrics.valid_snapshots`.
실제 금액이 나오는 출력과 `account.json`은 공유하지 않는다. 디렉터리는 gitignore 적용,
0700/0600 권한으로 저장한다. `workspace`도 실험마다 분리된다.

`health.cost_error`가 있으면 비용 확인 대기, `missing_or_stale_books`가 있으면
호가 신뢰도 문제다. `agent_error_count`와 `workspace/turns.jsonl`로 모델 장애를 구별한다.
`This shadow run already has an active runner`는 같은 실험의 중복 실행을 거절한 것이다.
모델 실패/프로세스 중단으로 남은 미완성 결정은 복원하며, 주문 승인 뒤 커서 저장 전에
중단되어도 같은 결정으로 중복 주문하지 않는다.

F43: 코드 동작 불변이어도 다음 콘솔 attach 시 HEAD 변경 때문에 기존 데몬이 한 번
자동 재시작되는 것은 정상이다. 진행 중인 모델 턴이 있다면 attach를 턴 사이로 미룬다.
이 작업에서 기존 데몬을 재시작하거나 실험을 장기 실행하지 않았다.

## 조절과 종료

`init` 옵션: `--days 7`, `--interval-minutes 60`, `--max-turns-per-day 8`,
`--latency-seconds 1`, `--slippage-bps 2`, `--participation 0.1`, `--symbols AAPL,MSFT,SPY`.
보유 종목은 선택 종목에 항상 합쳐진다. `run --poll-seconds 5`가 기본 관찰 간격이다.
Ctrl-C 또는 전용 systemd 서비스 중지로 종료한다. 만료 기한과 호출 한도는 재시작해도
늘어나지 않는다. 이미 진행 중인 모델 호출은 타임아웃 범위에서 끝날 수 있으나
종료 이후 해당 결정으로 주문하지 않는다. 주간 Codex 사용량을 읽는 기능은 아니다.
완전 롤백은 이 트랙의 merge commit에 `git revert -m 1 <merge-sha>`를 사용한다.

## 비용·성과 해석

- 가상 계좌의 순수익과 초기 자산을 그대로 보유한 경우를 같은 시세로 비교한다.
- 초기 자본은 사용 가능 USD + 미국 주식만 포함한다. 전체 Toss NAV/원화 수익률이 아니다.
- 현금 예약, bid/ask, 부분 체결, 수수료, 추정 SEC 비용을 반영한다. 미청산 포지션은 평가액이다.
- 연간 양도세와 FX는 별도다. 소액 수수료 면제는 보수적으로 가정하지 않는다.
- 규제비용은 API가 제공하지 않는 날짜별 추정이다. 2026-12-31 이후에는 검토 전 체결을 보류한다.
- 가상 손절/OCO는 실제 Toss 지원 기능이 아니다. 실제 주문 라우팅/취소 지연, queue priority,
  배당/분할/합병/ADR 비용, 결제 제약은 재현하지 않는다. 변동이 없으면 오래된 호가가 남을 수 있다.
- 10bps 추가 비용 결과는 비용 민감도이며 다른 지연 경로를 재생한 결과가 아니다.
- 단위 테스트 통과는 수익 개선 증거가 아니다. 며칠 데이터는 운용 장애/과다 회전 진단용이다.

## 검증 기록

2026-11-23 실제 공유 토큰으로 init → run --once → report 성공. 모델 호출/가상 체결 0회,
정규장 전 시장 닫힘 확인. 별도 강제 commissions 갱신 + AAPL 호가 파싱 성공.
HTTP hook으로 GET 이외 요청을 차단한 상태에서 GET 2회, 주문/토큰 발급 0회 확인.
계좌 수수료 0.001, 종료일 2026-11-24, 다음 날짜 00:00 KST 만료 계산을 확인했다.
시험 상태는 `research-comparisons/toss-shadow/smoke-20261123/`에만 저장했다.
금액/보유 내역/인증정보는 이 문서와 테스트 로그에 기록하지 않았다.
