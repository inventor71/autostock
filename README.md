# Autostock - 자동 주식 거래 시스템

미국 주식(NYSE/NASDAQ) 대상 자동 매매 시스템. 기술적 분석·ML·LLM 전략과, LLM이 포트폴리오를 직접 운용하는 에이전트 모드를 지원.

---

## 현재 할 수 있는 것

| 기능 | 설명 |
|------|------|
| **백테스팅** | 과거 데이터로 전략 성과 검증 (수익률, Sharpe, 최대낙폭 등) |
| **페이퍼 트레이딩** | Alpaca 모의 계좌에서 실제 시장과 동일한 조건으로 자동 매매 |
| **기술적 전략 4종** | MA Crossover, RSI, MACD, Bollinger Bands |
| **ML 전략 2종** | Random Forest, LSTM |
| **LLM 전략** | Claude/OpenAI가 OHLCV·뉴스를 분석해 신호 생성 (프롬프트 자동개선 루프 포함) |
| **에이전트 모드** | LLM PM이 매일 리서치→저널→결정을 작성하고, 결정론적 실행기가 RiskManager 경유로 브래킷 주문 실행 (`--mode agent`) |
| **앙상블** | 복수 전략을 투표/가중치 방식으로 결합 |
| **리스크 관리** | 포지션 사이징, 손절/익절 자동 실행, 브래킷(OCO) 주문, 서킷 브레이커 |
| **파라미터 최적화** | Grid search로 전략 파라미터 탐색 |
| **배치/실시간 모드** | 주기적 실행 또는 WebSocket 스트리밍 |

---

## 설치

```bash
# 의존성 설치
pip install -e ".[dev]"

# 환경 변수 설정 (Alpaca 페이퍼 트레이딩용)
export ALPACA_API_KEY="your-api-key"
export ALPACA_SECRET_KEY="your-secret-key"
```

Alpaca API 키는 https://app.alpaca.markets 에서 무료로 발급 가능합니다 (Paper Trading 계정).

---

## 사용법

### 1. 백테스트 실행

```bash
# 기본 설정으로 백테스트 (config/settings.yaml 기준)
python main.py --mode backtest

# 특정 종목 지정
python main.py --mode backtest --symbols AAPL MSFT SPY

# 디버그 로그
python main.py --mode backtest --log-level DEBUG
```

출력 예시:
```
==================================================
Strategy: ma_crossover | Universe: 2 symbols
Period: 2023-01-01 to 2024-01-01
==================================================
Total Return: 12.34%
Sharpe Ratio: 1.45
Max Drawdown: 8.21%
Total Trades: 15
Win Rate: 60.0%
Profit Factor: 2.13
Final Capital: $112,340.00
```

### 2. 페이퍼 트레이딩

```bash
# 배치 모드 (1시간 간격)
python main.py --mode paper

# 실시간 모드 (config/settings.yaml에서 trading.mode: realtime 설정)
python main.py --mode paper
```

### 2-1. 에이전트 모드 (LLM PM)

LLM 에이전트가 매일 리서치하고, 종목별 논지(thesis)와 결정(decision)을 저널에 기록하면,
결정론적 실행기가 RiskManager를 거쳐 브래킷 주문으로 체결합니다. 에이전트는 **자문 역할만** 하며
주문은 실행기만 넣습니다. 로컬 `claude` CLI(구독 인증)를 브레인으로 사용합니다.

```bash
# 오늘 세션 이어서 시작 (같은 날 재시작 시 리서치 생략)
python main.py --mode agent

# 깨끗한 세션으로 새로 시작
python main.py --mode agent --fresh
```

스케줄(ET): 장 시작 전 ~09:00 리서치 → 09:30 개장 시 실행 → 장중 N분마다 → 15:55 EOD 리뷰.
저널·결정·로그는 `workspace/`(gitignore)에 영속화됩니다. 모델은 `config/settings.yaml`의
`agent.model`(장중/EOD)·`agent.research_model`(리서치)로 설정합니다.

**장중 루프 재설계(F3, `--steering` 시 활성)**: 매 장중 턴에 Python이 조립한 구조화 brief
(가격/레벨/거리 + 계좌 진실 + 사람 개입 + 뉴스 diff)를 주입해 재계산을 없애고, 판단이 필요한
시장 이벤트(체결·비정상 움직임·watch 트리거·보호선 체결)에서 15분을 기다리지 않고 우선 발화하는
wake 턴을 추가합니다. 에이전트는 `watch set <SYM> <price_above|price_below|close_above|close_below>
<level>` 도구로 감시 조건을 등록하고, Python이 충족 시 깨워 ADJUST_STOP 여부를 판단하게 합니다
(자문-실행 분리 불변). 튜닝은 `config/settings.yaml`의 `intraday:` 블록.

### 2-2. 오퍼레이터 콘솔 (사람-개입 스티어링)

돌고 있는 에이전트를 사람이 **자연어로 개입**하기 위한 콘솔입니다(예: "AAPL 절반 팔아", "신규 진입 멈춰", 일시정지). 에이전트는 자문만 하고 **주문 권한이 없으며**, 콘솔도 직접 주문하지 않습니다 — 데몬과는 레포 루트 `steering/` 파일드롭 채널로만 통신하고, **사람 확인 + `RiskManager→Broker` 게이트**가 유일한 경계입니다. 콘솔은 trader용으로 리브랜드한 opencode 포크(`operator-console/`)입니다.

```bash
# 1) 한 번 설치 — ~/.local/bin/autostock 런처 생성 (+ systemd --user 유닛)
bun operator-console/launcher/install.ts

# 2) 실행 — preflight(키/포트 등 점검, 문제 시 안전하게 중단) → 데몬이 꺼져 있으면
#    systemd --user로 자동 기동, 이미 떠 있으면 거기에 attach
autostock
```

콘솔의 **사이드바**는 run-state·시장 상태·포지션(+락)·대기 승인과 계좌·라운드트립(승률/실현손익) 요약을 보여주며, 마우스로 폭을 드래그 조절할 수 있습니다. (기능 묶음: F4 파일드롭 콘솔 + F5 `autostock` 런처/데몬 관리·리브랜드 + F6 사이드바.)

### 3. 전략 변경

`config/strategies.yaml`에서 활성 전략 변경:

```yaml
# 단일 전략
active_strategies:
  - rsi

# 복수 전략 (각각 독립 실행)
active_strategies:
  - ma_crossover
  - rsi
  - macd
```

### 4. 파라미터 조정

`config/strategies.yaml`에서 각 전략의 파라미터 수정:

```yaml
strategies:
  ma_crossover:
    params:
      fast_period: 10    # 단기 이평선
      slow_period: 30    # 장기 이평선

  rsi:
    params:
      period: 14
      overbought: 70     # 매도 신호 기준
      oversold: 30       # 매수 신호 기준
```

### 5. 리스크 설정

`config/settings.yaml`에서 조정:

```yaml
risk:
  max_position_pct: 0.1    # 포트폴리오의 최대 10%까지 한 종목에 투자
  stop_loss_pct: 0.05      # 5% 손실시 자동 손절
  take_profit_pct: 0.15    # 15% 이익시 자동 익절
  max_open_positions: 10   # 최대 동시 보유 종목 수
```

### 6. Python에서 직접 사용

```python
from src.data.providers.yfinance_provider import YFinanceProvider
from src.strategy.technical.ma_crossover import MovingAverageCrossover
from src.backtest.engine import BacktestEngine

# 데이터 가져오기
provider = YFinanceProvider()
bars = provider.get_bars("AAPL", limit=200)

# 백테스트 실행
strategy = MovingAverageCrossover({"fast_period": 10, "slow_period": 30})
engine = BacktestEngine(strategy=strategy, initial_capital=100000)
result = engine.run("AAPL", bars)

print(f"수익률: {result.total_return_pct:.2f}%")
print(f"샤프비율: {result.sharpe_ratio:.2f}")
```

### 7. 파라미터 최적화

```python
from src.backtest.optimizer import ParameterOptimizer
from src.strategy.technical.ma_crossover import MovingAverageCrossover

optimizer = ParameterOptimizer(
    strategy_class=MovingAverageCrossover,
    param_grid={
        "fast_period": [5, 10, 15, 20],
        "slow_period": [30, 40, 50, 60],
    },
    metric="sharpe_ratio",
)

best_params, best_result, all_results = optimizer.optimize("AAPL", bars)
print(f"최적 파라미터: {best_params}")
```

### 8. ML 전략 학습

```python
from src.data.providers.yfinance_provider import YFinanceProvider
from src.strategy.ml.rf_strategy import RandomForestStrategy

provider = YFinanceProvider()
bars = provider.get_bars("AAPL", limit=500)

# 학습
strategy = RandomForestStrategy({"n_estimators": 200})
strategy.train(bars)
strategy.save_model("./models/rf_aapl.pkl")

# 시그널 생성
signal = strategy.generate_signal("AAPL", bars)
print(f"{signal.signal.value} (confidence: {signal.confidence:.2f})")
```

---

## 테스트

```bash
python -m pytest tests/ -v
```

---

## 프로젝트 구조 요약

```
autostock/
├── main.py                 # 진입점 (--mode backtest/paper/live/agent)
├── config/                 # 설정 파일
├── src/
│   ├── core/               # 타입, 모델, 예외
│   ├── data/providers/     # 데이터 수집 (yfinance, alpaca, 뉴스)
│   ├── strategy/           # 전략 (technical, ml, llm, ensemble)
│   ├── execution/brokers/  # 주문 실행 (alpaca, simulated)
│   ├── risk/               # 리스크 관리 (사이징, 브래킷, 서킷브레이커)
│   ├── backtest/           # 백테스트 엔진
│   ├── trading/            # 트레이딩 엔진 + 스케줄러 + 실행 모드(batch/realtime/agent)
│   ├── agent/              # 에이전트 모드 (LLM PM 오케스트레이터 + 결정 실행기 + 저널)
│   └── monitoring/         # 로깅, 알림
└── tests/                  # 테스트 (pytest)
```

> 자세한 내부 구조·설계 의도는 [docs/DESIGN.md](docs/DESIGN.md) 참고.
