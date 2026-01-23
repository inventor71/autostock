# Autostock - 자동 주식 거래 시스템

미국 주식(NYSE/NASDAQ) 대상 자동 매매 시스템. 기술적 분석부터 ML 전략까지 지원.

---

## 현재 할 수 있는 것

| 기능 | 설명 |
|------|------|
| **백테스팅** | 과거 데이터로 전략 성과 검증 (수익률, Sharpe, 최대낙폭 등) |
| **페이퍼 트레이딩** | Alpaca 모의 계좌에서 실제 시장과 동일한 조건으로 자동 매매 |
| **기술적 전략 4종** | MA Crossover, RSI, MACD, Bollinger Bands |
| **ML 전략 2종** | Random Forest, LSTM |
| **앙상블** | 복수 전략을 투표/가중치 방식으로 결합 |
| **리스크 관리** | 포지션 사이징, 손절/익절 자동 실행 |
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
Strategy: ma_crossover | Symbol: AAPL
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
├── main.py                 # 진입점 (--mode backtest/paper)
├── config/                 # 설정 파일
├── src/
│   ├── core/               # 타입, 모델, 예외
│   ├── data/providers/     # 데이터 수집 (yfinance, alpaca)
│   ├── strategy/           # 전략 (technical, ml, ensemble)
│   ├── execution/brokers/  # 주문 실행 (alpaca, simulated)
│   ├── risk/               # 리스크 관리
│   ├── backtest/           # 백테스트 엔진
│   ├── trading/            # 트레이딩 엔진 + 스케줄러
│   └── monitoring/         # 로깅, 알림
└── tests/                  # 테스트 (42개)
```
