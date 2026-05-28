# Autostock 설계 문서

> 미국 주식(NYSE/NASDAQ) 자동 매매 시스템의 아키텍처 설계 문서.
> 사용법은 [README.md](../README.md)를, 본 문서는 내부 구조·설계 의도·확장 방법을 다룬다.

---

## 1. 개요

Autostock은 **데이터 수집 → 신호 생성 → 리스크 관리 → 주문 실행**의 파이프라인을 추상화한 자동 매매 프레임워크다. 두 가지 오케스트레이션 경로를 제공한다:

- **전략 경로**(원형): 동일한 전략 코드를 **백테스트 / 페이퍼 트레이딩 / 실시간 매매** 모드에서 그대로 재사용. `TradingEngine`이 심볼별로 전략을 돌린다.
- **에이전트 경로**(신규): LLM "포트폴리오 매니저"가 책 전체를 매일 추론해 결정을 저널에 쓰고, 결정론적 `DecisionExecutor`가 이를 브래킷 주문으로 체결한다(`--mode agent`). → §5.8 참고.

핵심 특징:

- **플러그형 추상화**: 데이터 제공자, 브로커, 전략이 각각 추상 베이스 클래스(`BaseDataProvider`, `BaseBroker`, `BaseStrategy`)를 구현하므로 교체·확장이 자유롭다.
- **전략 다양성**: 기술적 분석 4종, ML 2종, LLM, 앙상블을 동일 인터페이스로 제공.
- **백테스트-실거래 일관성**: `RiskManager`와 전략 로직을 백테스트와 실거래가 공유하여 결과 괴리를 최소화.
- **LLM 자기개선 루프**: 백테스트 결과를 LLM이 분석해 트레이딩 프롬프트를 자동으로 버전업.
- **에이전트 PM**: 두 번째 경로로, LLM이 자문(저널 작성)을 맡고 실행은 결정론적 Python(RiskManager → Broker)이 전담하는 brain/body 분리 구조.

---

## 2. 설계 원칙

| 원칙 | 적용 방식 |
|------|-----------|
| **관심사 분리** | data / strategy / risk / execution / trading / backtest 레이어로 디렉토리 분리 |
| **인터페이스 우선** | 각 레이어는 ABC로 계약을 정의하고, 구현체는 `providers/`·`brokers/` 하위에 격리 |
| **의존성 역전** | `TradingEngine`은 구체 클래스가 아닌 베이스 추상화에만 의존 (DI로 주입) |
| **타입 안정성** | 모든 도메인 객체는 Pydantic 모델(`src/core/models.py`), 열거형은 `src/core/types.py` |
| **설정 외부화** | 코드 변경 없이 YAML/환경변수로 동작 제어 (`config/`) |
| **레지스트리 패턴** | 전략은 데코레이터로 자가 등록되어 이름 문자열만으로 인스턴스화 가능 |

---

## 3. 시스템 아키텍처

```
                          ┌──────────────┐
                          │   main.py    │  CLI 진입점 / 모드 분기
                          └──────┬───────┘
                                 │ DI (provider, broker, strategies, risk)
                ┌────────────────┼────────────────────────┐
                ▼                ▼                         ▼
        ┌───────────────┐  ┌──────────────┐       ┌────────────────┐
        │  Backtest     │  │   Trading    │       │  LLM 자기개선   │
        │  Engine       │  │   Engine     │       │  (auto_improver)│
        └───────┬───────┘  └──────┬───────┘       └────────┬───────┘
                │                  │ run_cycle()            │
                │      ┌───────────┴───────────┐            │
                │      ▼           ▼           ▼            │
                │  [Batch모드]  [Realtime모드] [Scheduler]   │
                │      └───────────┬───────────┘            │
                │                  │                        │
        ════════╪══════════════════╪════════════════════════╪═══════
                ▼                  ▼                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │                    공유 파이프라인                          │
        │                                                            │
        │  DataProvider ──▶ Strategy ──▶ RiskManager ──▶ Broker      │
        │   (get_bars)    (generate_   (evaluate_       (submit_     │
        │                  signal)      signal)          order)      │
        └──────────────────────────────────────────────────────────┘
                │                  │                        │
                ▼                  ▼                        ▼
        yfinance/Alpaca    technical/ml/llm/        Simulated /
                            ensemble                 Alpaca Broker
```

> 위 다이어그램은 **전략 경로**(backtest/paper/realtime)를 나타낸다. **에이전트 경로**(`--mode agent`)는
> `TradingEngine`을 거치지 않고 별도 루프를 돈다 — LLM PM(brain)이 저널에 결정을 쓰고, `DecisionExecutor`(body)가
> 같은 `RiskManager`·`Broker`로 체결한다. 상세는 §5.8.

**레이어 의존 방향**: `trading`·`backtest`·`agent` → `strategy`·`risk`·`execution`·`data` → `core`
(상위 레이어만 하위를 참조하며, `core`는 누구에게도 의존하지 않는다.)

---

## 4. 핵심 도메인 모델

`src/core/`는 전 레이어가 공유하는 타입의 단일 출처(single source of truth)다.

### 4.1 열거형 (`types.py`)

- `Signal`: `BUY / SELL / HOLD` — 전략 출력
- `OrderSide`: `buy / sell` — 브로커 주문 방향
- `OrderType`: `market / limit / stop / stop_limit`
- `TimeFrame`: `1m ~ 1mo` — 봉 주기
- `TradingMode`: `paper / live / backtest`
- `PositionSide`: `long / short`

### 4.2 데이터 모델 (`models.py`)

```
Bar              OHLCV 단일 봉
TradeSignal      전략 출력 (signal, confidence 0~1, sell_pct, metadata)
Order            브로커 제출용 주문 (side, qty, order_type, ...)
FilledOrder      체결 결과 (filled_price, filled_at, commission)
Position         보유 포지션 (qty, avg_entry_price, unrealized_pnl)
                 └ update_price()로 시가평가 갱신, cost_basis 프로퍼티
PortfolioState   계좌 스냅샷 (cash, equity, positions dict)
                 └ total_value / position_count 프로퍼티
BacktestResult   백테스트 성과 (수익률, Sharpe, MDD, 승률, equity_curve)
```

**설계 포인트**: `TradeSignal`은 단순 방향이 아니라 `confidence`(포지션 사이징에 활용)와 `sell_pct`(부분 청산 지원)를 함께 전달한다. `metadata`로 LLM의 추론 근거 등 전략별 부가정보를 실어 보낼 수 있다.

---

## 5. 레이어별 상세 설계

### 5.1 Data 레이어 (`src/data/`)

```
BaseDataProvider (ABC)
├─ get_bars(symbol, timeframe, start, end, limit) -> DataFrame  [추상]
├─ get_latest_price(symbol) -> float                            [추상]
└─ get_multiple_bars(...)  -> dict[symbol, DataFrame]           [기본구현]

구현체:
├─ YFinanceProvider        무료, 기본값. 백테스트 데이터 소스
├─ AlpacaProvider          실시간/페이퍼 트레이딩용
└─ YFinanceNewsProvider    LLM 전략의 뉴스 컨텍스트 (news_provider.py)
```

모든 봉 데이터는 `[open, high, low, close, volume]` 컬럼 + `DatetimeIndex` 규약을 따른다. 이 규약 덕분에 전략은 데이터 출처를 몰라도 동작한다.

### 5.2 Strategy 레이어 (`src/strategy/`)

모든 전략은 `BaseStrategy`를 구현하며, **핵심 계약은 단 하나**다:

```python
generate_signal(symbol, bars, portfolio) -> TradeSignal
```

추가로 두 가지 선택적 훅을 제공한다:

- `supports_selection() -> bool`: 동적 심볼 선정 지원 여부
- `select_symbols(universe, market_data, portfolio) -> list[str]`: universe에서 거래할 심볼을 동적 선정 (모멘텀 스크리닝, 섹터 로테이션 등). 기본값은 전체 universe.

#### 전략 레지스트리 (`registry.py`)

```python
@register_strategy("rsi")          # 데코레이터로 _REGISTRY에 자가 등록
class RSIStrategy(BaseStrategy): ...

create_strategy("rsi", params)     # 이름 문자열 → 인스턴스 (팩토리)
```

`main.py`는 전략 모듈을 import하여 등록을 트리거한 뒤, `strategies.yaml`의 `active_strategies` 목록을 이름으로 인스턴스화한다.

#### 전략 분류

| 분류 | 위치 | 종류 |
|------|------|------|
| 기술적 | `technical/` | MA Crossover, RSI, MACD, Bollinger Bands |
| 머신러닝 | `ml/` | RandomForest, LSTM (+ `feature_eng.py`) |
| LLM | `llm/` | Claude/OpenAI 기반 분석 전략 |
| 앙상블 | `ensemble/` | Voting(다수결), Weighted(가중치) |

**ML 전략 (`BaseMLStrategy`)**: `BaseStrategy`를 확장하여 `build_features / train / predict / save_model / load_model`을 추가 계약으로 둔다. `generate_signal`은 베이스에서 "모델 로드 확인 → 피처 빌드 → 마지막 행 예측" 흐름을 공통 구현하고, 서브클래스는 모델 세부만 채운다. 모델 가중치는 `models/`에 영속화되며 `model_path` 파라미터로 로드.

**앙상블 (`VotingEnsemble`)**: 내부에 여러 전략을 담고(`add_strategy`), 각 전략의 신호를 수집해 다수결 투표. `min_agreement`(기본 0.6) 이상 합의 시에만 해당 신호를 채택하고, 신뢰도는 `평균 신뢰도 × 합의율`로 산출한다.

#### LLM 전략 서브시스템 (`src/strategy/llm/`)

가장 복잡한 모듈로, 6개 컴포넌트로 구성된다:

```
llm_strategy.py    LLMStrategy — generate_signal 구현. 데이터 포맷 → LLM 호출
                   → JSON 파싱(3단계 폴백) → TradeSignal 변환
client.py          BaseLLMClient + ClaudeClient / OpenAIClient
                   └ create_llm_client() 팩토리, 지수 백오프 재시도 내장
data_formatter.py  OHLCV·뉴스를 LLM 프롬프트용 텍스트로 변환, 토큰 절단
prompt_manager.py  프롬프트 버전 관리 (v1, v2, ...). JSON 히스토리 영속화,
                   버전별 백테스트 성과 기록, latest/best 조회
auto_improver.py   백테스트 결과 분석 → LLM에 개선 요청 → 새 프롬프트 버전 생성
prompt_manager.py  PromptVersion / PromptHistory / BacktestMetrics 모델
```

**견고성 설계**: LLM 응답은 비결정적이므로 `_parse_llm_response`가 ①직접 JSON 파싱 ②마크다운 코드펜스 추출 ③정규식 객체 추출 ④키워드 폴백(낮은 신뢰도) 순으로 단계적으로 처리한다. 어떤 단계에서도 실패하면 `HOLD`를 반환해 안전하게 작동한다.

### 5.3 Risk 레이어 (`src/risk/`)

신호를 실제 주문으로 변환하는 **게이트키퍼**다. 전략과 브로커 사이에 위치한다.

```
RiskManager
├─ evaluate_signal(signal, price, portfolio) -> Order | None
│   ├─ BUY:  최대 포지션 수 체크 → 중복 보유 차단 → 사이징 → Order
│   └─ SELL: 보유 확인 → sell_pct 적용(부분청산) → Order
├─ check_stop_loss(portfolio)   -> list[Order]   손절 트리거
└─ check_take_profit(portfolio) -> list[Order]   익절 트리거

PositionSizer
└─ calculate_shares(...) -> int
    min(최대배분, 리스크기반배분) × confidence, 가용현금 한도
```

**리스크 파라미터** (config 기본값):
- `max_position_pct=0.1` — 종목당 최대 10%
- `max_portfolio_risk=0.02` — 거래당 포트폴리오 리스크 2%
- `stop_loss_pct=0.05` / `take_profit_pct=0.15`
- `max_open_positions=10`

**포지션 사이징 공식**: 고정비율 배분(`equity × max_position_pct`)과 리스크기반 배분(`equity × max_portfolio_risk / stop_loss_pct`) 중 작은 값을 택하고, 신호 신뢰도로 스케일한 뒤 가용 현금으로 한 번 더 제한한다.

### 5.4 Execution 레이어 (`src/execution/`)

```
BaseBroker (ABC)
├─ submit_order(order) -> FilledOrder
├─ get_position / get_all_positions / get_portfolio_state
├─ cancel_order / close_position

구현체:
├─ SimulatedBroker   백테스트용. 즉시 체결, 평단가 갱신, 현금/포지션 장부 관리
│                    └ set_current_price()로 봉마다 시세 주입, reset()으로 초기화
└─ AlpacaBroker      실거래/페이퍼. Alpaca API 래핑
```

`SimulatedBroker`는 매수 시 현금 부족·매도 시 미보유/수량초과를 `BrokerError`로 막아 백테스트의 현실성을 보장한다. 동일한 `BaseBroker` 계약 덕분에 `TradingEngine`은 시뮬레이션인지 실거래인지 구분하지 않는다.

### 5.5 Trading 오케스트레이션 (`src/trading/`)

#### TradingEngine — 실거래 파이프라인의 심장

```python
run_cycle() -> list[FilledOrder]:
    1. 포트폴리오 조회
    2. _check_risk_exits()        # 손절/익절 먼저 검사·실행
    3. _load_market_data()        # universe 전체 봉 로드
    4. for 전략 in strategies:
         selected = 전략.select_symbols(...) if supports_selection else universe
         for 심볼 in selected:
             signal = 전략.generate_signal(심볼, bars, portfolio)
             _process_signal()    # 시세조회 → 리스크평가 → 주문제출
         포트폴리오 갱신
```

각 단계가 try/except로 격리되어 한 심볼·전략의 실패가 전체 사이클을 중단시키지 않는다.

#### 실행 모드 (`modes/`)

| 모드 | 트리거 | 용도 |
|------|--------|------|
| `BatchTradingMode` | APScheduler 주기 실행(기본 60분) | 정기 리밸런싱 |
| `RealtimeTradingMode` | Alpaca WebSocket 봉 수신 | 실시간 반응 매매 (봉마다 `run_cycle_for_symbol`로 해당 심볼만 처리) |

#### TradingScheduler (`scheduler.py`)

APScheduler 래퍼. 인터벌 작업뿐 아니라 미국장 개장(09:30 ET)·마감(15:55 ET) cron 잡을 지원한다.

### 5.6 Backtest 레이어 (`src/backtest/`)

```
BacktestEngine
└─ run(universe, bars, warmup_period) -> BacktestResult
    워밍업 이후 봉 단위로 순회:
      ├ 전 심볼 시세 갱신 (broker.set_current_price)
      ├ 손절/익절 검사
      ├ market_data = 각 심볼의 iloc[:i+1]  (룩어헤드 방지)
      ├ 전략 신호 생성 → 리스크 평가 → 시뮬 체결
      └ equity 기록
    → generate_report()로 성과 지표 산출

metrics.py    Sharpe / Sortino / Calmar / MDD / 승률 / Profit Factor
optimizer.py  ParameterOptimizer — param_grid 전수조합 그리드서치
```

**룩어헤드 편향 방지**: 백테스트는 시점 `i`에서 `bars.iloc[:i+1]`만 전략에 전달하여 미래 데이터 누수를 차단한다. 단일/다중 심볼 모두 지원하며(`run("AAPL", df)` 또는 `run([...], dict)`), 실거래 엔진과 동일한 `RiskManager`·전략을 사용해 백테스트-실거래 일관성을 확보한다.

### 5.7 Monitoring (`src/monitoring/`)

- `logger.py`: loguru 기반 로깅 설정 (`setup_logging`)
- `alerts.py`: Slack/Telegram 알림 (config의 `monitoring`에서 토글)

### 5.8 Agent 경로 (`src/agent/`) — LLM 포트폴리오 매니저

전략 경로와 별개의 두 번째 오케스트레이션 경로다. `TradingEngine`이 심볼별로 도는 것과 달리,
LLM PM이 **책 전체를 한 턴에** 추론한다. **brain/body 분리**가 핵심 설계다: LLM은 자문(저널 작성)만 하고,
주문은 결정론적 Python만 넣는다.

```
AgentTradingMode (trading/modes/agent.py)   장중 인식 스케줄로 두 축을 합성
├─ AgentTradingLoop (orchestrator.py)   brain: 일일 턴(리서치/장중/EOD) 시퀀싱
│   └─ AgentSession (session.py)        로컬 `claude -p` CLI를 하루 단위 세션으로 래핑
│        └─ Journal (journal.py)        파일 기반 영속 메모리(durable memory)
│             ├─ decisions.jsonl        기계 실행용 Decision 라인(append-only)
│             ├─ positions/<SYM>.md     종목별 논지(thesis)·계획(entry/stop/target)
│             └─ regime/watchlist/lessons.md
└─ DecisionExecutor (executor.py)       body: 결정을 읽어 실행 — 유일한 주문 경로
     ├─ 풀 제약·만료·서킷브레이커 검사
     ├─ RiskManager(브래킷 모드) → Broker
     └─ 커서(.executor_state.json)로 멱등 실행
```

**핵심 설계 포인트**:

- **brain/body 분리**: 에이전트는 `decisions.jsonl`에 제안을 append할 뿐, 실행기만 주문을 넣는다.
  실행기는 모든 결정을 다른 경로와 **동일한 게이트**(`RiskManager` → `Broker`)에 통과시킨다.
- **저널 = 단일 진실 출처**: 일일 CLI 세션은 하루 안의 연속성만 담당하고, 날짜가 바뀌면 새 세션을 쓴다.
  durable state는 전부 `workspace/`의 파일(gitignore된 런타임 상태).
- **멱등 실행**: 커서가 처리한 결정 라인 수를 기록해, 재실행해도 동일 브래킷을 한 번만 제출한다
  (이후엔 거래소가 OCO를 보유).
- **자문-실행 시간 분리**: 리서치는 장 시작 전에 앞서 돌 수 있지만(`is_market_open`이 False면 결정은 pending 유지),
  실행은 정규장에서만 일어난다.
- **텔레메트리/장부**: `turn_log`(턴별 비용), `equity_log`(일일 자산 vs 벤치마크), `trades_log`(완료된 라운드트립),
  `review.py`(EOD 셀프리뷰 → lessons.md).

> 참고: 실행기가 Alpaca에 한해 trade-ledger를 재구성할 때 브로커의 비공개 속성에 접근하는 등 일부 누수가 있다 —
> §9 및 `aidlc-docs/inception/reverse-engineering/code-quality-assessment.md`(S-4) 참고.

---

## 6. 주요 데이터 흐름

### 6.1 실거래 한 사이클 (Batch/Realtime 공통)

```
DataProvider          Strategy           RiskManager         Broker
     │                   │                    │                 │
     │ get_bars()        │                    │                 │
     │◀──────────────────┤                    │                 │
     │  OHLCV DataFrame   │                    │                 │
     │──────────────────▶│ generate_signal()  │                 │
     │                   │── TradeSignal ────▶│ evaluate_signal()│
     │                   │                    │── Order ────────▶│ submit_order()
     │                   │                    │                 │── FilledOrder ─▶
```

### 6.2 LLM 프롬프트 자기개선 루프

```
백테스트 실행 (llm 전략)
     │  BacktestResult[]
     ▼
PromptManager.record_backtest_result()   ← 버전별 성과 누적
     │
     ▼
PromptAutoImprover.analyze_and_improve()
     ├─ 성과 집계 + 이슈 자동 진단 (_identify_issues: 음수수익/낮은Sharpe/과매매 등)
     ├─ LLM에 "현재 프롬프트 + 성과 + 이슈" 전달
     └─ 개선된 프롬프트 JSON 수신 → 파싱
     │
     ▼
PromptManager.save_prompt(parent_version=...)   ← v2, v3 ... 으로 버전업
     │
     ▼
(재백테스트하여 개선 검증 — 현재는 수동/반복 호출)
```

`main.py --improve-prompt --improvement-iterations N`으로 구동한다.

---

## 7. 확장 가이드

### 새 전략 추가
1. `src/strategy/<분류>/my_strategy.py` 생성
2. `BaseStrategy` 상속 + `@register_strategy("my_strategy")`
3. `generate_signal()` 구현 (필요 시 `select_symbols()` 오버라이드)
4. `main.py`의 import 목록에 추가 (등록 트리거)
5. `config/strategies.yaml`의 `strategies`에 정의 + `active_strategies`에 추가

### 새 데이터 제공자 추가
1. `src/data/providers/my_provider.py`에서 `BaseDataProvider` 구현
2. `get_bars` / `get_latest_price` 구현 (OHLCV+DatetimeIndex 규약 준수)
3. `main.py:create_data_provider()`에 분기 추가

### 새 브로커 추가
1. `src/execution/brokers/my_broker.py`에서 `BaseBroker` 구현
2. 6개 추상 메서드 모두 구현
3. `main.py:create_broker()`에 분기 추가

---

## 8. 설정 체계 (`config/`)

```
config.py          Pydantic Settings — YAML + .env + 환경변수 병합
                   └ get_settings() (lru_cache로 싱글톤)
settings.yaml      앱/브로커/데이터/트레이딩/리스크/백테스트/LLM 설정
strategies.yaml    전략 정의·파라미터·active 목록·앙상블 구성
prompts/           트레이딩 프롬프트 텍스트 + 버전 히스토리 JSON
.env               API 키 (alpaca/anthropic/openai) — 커밋 금지
```

**우선순위**: CLI 인자 > 환경변수 > `.env` > YAML > 코드 기본값.
환경변수는 `env_nested_delimiter="__"`로 중첩 설정 접근 (예: `RISK__STOP_LOSS_PCT`).

---

## 9. 알려진 이슈 / 개선 포인트

> 설계 검토 중 발견된 사항. 향후 작업 시 참고. 상세·증거·수정안은
> `aidlc-docs/inception/reverse-engineering/code-quality-assessment.md` 참고.

**열린 이슈 (보류)**:

1. **`get_status()`의 하드코딩** (`trading/engine.py:278` 부근): `"mode": "live"` 고정. (Q-3)
2. **LLM 개선 루프의 재백테스트 미자동화**: `_run_prompt_improvement`가 새 프롬프트로 자동 재백테스트하지 않아, 반복 개선 시 동일 성과 데이터를 재사용한다.
3. **`PortfolioState.total_value` 죽은 중복** (M-1): 아무도 안 읽으며 `equity` 필드와 발산 가능. 제거하거나 단일화 권장.
4. **테스트 공백** (Q-4): `TradingEngine`·LLM 서브시스템·데이터 제공자·`AgentSession`은 아직 무테스트.
5. **숏 포지션 미지원** (H-1): `PositionSide.SHORT` 열거형은 있으나 리스크/실행 로직은 롱 온리 가정.

> **해결됨**:
> - `RealtimeTradingMode`의 `engine.symbols` → `engine.universe` 속성 불일치, 및 봉 수신마다 universe 전체를 재로드하던 비효율(`run_cycle_for_symbol`로 틱된 단일 심볼만 처리).
> - 구조 리팩터링 S-5/S-3/S-1+S-2/S-4 (위 1~4번) 완료.
> - **백테스트 정합성 (B-1/B-2)**: 메트릭이 라운드트립 기반(`src/core/trades.py::match_round_trips` 공유), 스탑/익절이 봉 high/low로 장중 트리거(resting OCO)되어 실거래와 일치. `BacktestResult.trades`도 채워짐.
> - **소수 포지션 매도 (B-3)**: `_handle_sell`의 int 절삭·최소 1주 강제 제거 — 전량청산은 정확한 보유수량, fractional 안전.

---

*이 문서는 코드베이스(`src/`, `config/`, `main.py`) 분석을 바탕으로 작성되었다. 구조 변경 시 함께 갱신할 것.*
