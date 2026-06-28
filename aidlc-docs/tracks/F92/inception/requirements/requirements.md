# F92 Requirements — 브로커 provider 정합성 버그 수정 + 멀티 인스턴스 격리 복구

**Depth**: standard · **Type**: bugfix + native refactor + ops surgery · **Brownfield**

## 1. 문제 (확인됨, 라이브)

운영 중 Docker prod 3개 인스턴스(aggressive/balanced/conservative)는 각각 distinct
account_farm sub-account로 거래하며 **데몬 주문실행 격리는 정상**(`main.py::create_broker()`
provider-aware 사용). 그러나 agent가 broker-truth(손익/포지션/주문)를 읽는 **CLI 경로가
provider를 무시하고 `AlpacaBroker`를 하드코딩** → 3 인스턴스가 동일한 ALPACA_API_KEY를
공유하므로 **공유 Alpaca 페이퍼 계좌 하나**를 읽는다.

결과: agent가 자기 실 sub-account 보유분을 못 보고, 공유 Alpaca 계좌의 **pre-docker 유령
포지션(RTX/TMO)** 기준으로 의사결정·기록해 왔다. (표시 오류 + 의사결정 정합성 훼손)

### 라이브 검증
| 인스턴스 | 실 sub-account (account_farm) | agent가 보던 것 (공유 Alpaca) |
|---|---|---|
| aggressive (8eec) | HD 4 @342.61, eq 79,651 | RTX19/TMO5, eq 99,939 |
| balanced (75aa) | HON 9 @228.84, eq 75,928 | RTX19/TMO5, eq 99,939 |
| conservative (6ddc) | GILD 14 @126.47, eq 51,254 | RTX19/TMO5, eq 99,939 |

→ 계좌 격리 자체는 정상(서로 다름). RTX/TMO는 어느 sub-account에도 없음.

## 2. 영향 지점 (격리 전수 점검 결과)

**계좌 truth 우회 (수정 대상 — provider 무시):**
1. `src/agent/tools/__main__.py::_broker()` — `python -m src.agent.tools account`, 시그널 held-lookup. **[critical, 결정경로]**
2. `src/agent/logs/equity.py::main()` — `python -m src.agent.logs.equity`, equity.jsonl 기록. **[critical, 손익이력]**
3. `scripts/status.py:180` — 운영자 대시보드(`monitor.sh` 전용), Alpaca 내부 client 의존. **[secondary, 결정경로 밖]**

**공유가 정상인 지점 (시장데이터 — 계좌 무관, 수정 안 함):**
- `src/data/intraday/collector.py:134`, `src/signals/collector.py:365-370`,
  `main.py:323` (`_make_signal_brief_provider`) — 모두 alpaca **시장데이터** 용도.
  ALPACA_*는 공유 market-data 키이므로 공유가 의도된 정상 동작.
- `config_env.py` — 키 존재 여부 health check만.

**경계/후속 (이번 트랙 out-of-scope, 문서화):**
- `src/benchmark/runner.py:103` — `AccountFarmBroker` 직접 생성(파라미터 주입). benchmark는
  account_farm 전제. backtest/benchmark 폐기 예정([[backtest-deprecation-pending]])이라 보류.

## 3. 목표 / 수용 기준

1. **코드 정합성**: 계좌 truth를 읽는 모든 경로가 `create_broker(settings)`(provider-aware)를
   거친다. account_farm 설정이면 AccountFarmBroker, alpaca면 AlpacaBroker, kis면 KIS.
   - AC: 컨테이너에서 `python -m src.agent.tools account`가 해당 인스턴스의 account_farm
     sub-account(예: aggressive=HD4, eq 79,651)를 반환.
   - AC: `python -m src.agent.logs.equity`가 sub-account equity를 기록.
2. **native refactor**: `create_broker`를 `src/execution/brokers/factory.py`로 추출하고
   모든 호출부가 거기서 import(현 `from main import create_broker` upward 의존 제거).
   원래 그 구조였던 듯 읽히게([[feedback-monorepo-refactor-as-native]]).
3. **회귀 방지 테스트**: provider→broker 클래스 매핑 + 에이전트 CLI/equity가 팩토리 경유임을 검증.
4. **운영 surgery (리셋+reconcile, 사용자 결정)**: 코드 배포 후 3개 컨테이너 각각
   workspace의 거래상태 파일을 비우고(또는 아카이브) 데몬이 자기 sub-account truth로
   재구축하게 한다. 실보유 HD/HON/GILD 포지션은 유지(청산 안 함).
   - AC: surgery 후 각 인스턴스 콘솔 `account`가 자기 실 sub-account만 보고(유령 RTX/TMO 소멸).

## 4. 비목표 (Out of Scope)
- account_farm sandbox 내부 구현 변경, 새 계좌 발급.
- 시장데이터 공유 구조 변경(정상).
- benchmark/backtest 경로(폐기 예정).
- 실보유 포지션 청산(사용자가 유지 선택).

## 5. 결정 로그
- Surgery = 리셋+reconcile, 실보유 유지 (UAQ 2026-06-28).
- Security Baseline / PBT extension = Disabled (UAQ 2026-06-28).
