# F70 / benchmark — Functional Design

## 1. 데이터 모델 (pydantic, `src/benchmark/models.py`)

### EquitySnapshot (원천 시계열 레코드)
```
ts: datetime           # 스냅샷 시각 (UTC)
strategy: str          # baseline 전략명 또는 "llm"
account_masked: str    # 마스킹된 계정 식별자 (시크릿 미포함 — SECURITY)
equity: float          # PortfolioState.equity (단일 출처)
cash: float
position_count: int
```
- JSONL 1줄 = 1레코드. `src/core/jsonl.append_record` 재사용.
- **불변식**: equity/cash ≥ 0 가정 안 함(공매도/마진 가능). NaN/inf 금지(기록 전 검증).

### BaselineMetric / BenchmarkMetrics (파생 지표)
```
BaselineMetric:
  strategy: str
  cum_return: float       # (마지막 equity / 첫 equity) - 1
  volatility: float       # 일간(또는 스냅샷 간) 수익률 표준편차
  max_drawdown: float     # 최저점 낙폭 (음수)
  sharpe: float           # 평균/표준편차 * sqrt(annualization) — rf=0 가정

BenchmarkMetrics:
  ts: datetime            # 산출 시각
  window_start/window_end: datetime
  llm: BaselineMetric
  baselines: list[BaselineMetric]
  alpha: dict[str,float]  # {strategy: llm.cum_return - baseline.cum_return}
  n_points: dict[str,int] # 전략별 스냅샷 수 (정합성 확인용)
```

## 2. 비즈니스 규칙

- **BR-1 (buy&hold).** `generate_signal(symbol, bars, portfolio)`:
  - `portfolio`가 None이거나 `symbol not in portfolio.positions` → `BUY` (confidence 1.0).
  - 이미 보유 → `HOLD`. → 엔진 per-symbol 루프가 "유니버스 각 종목 1회 매수 후 보유"를 구현.
  - bars가 비면 `InsufficientDataError` (다른 전략과 동일 계약). 지표 계산 불필요(가격 무관).
- **BR-2 (fail-closed 빌드).** baseline 전략의 계정 매핑이 없거나 `BrokerApiBroker` 생성이
  실패(`BrokerError`)하면 그 baseline만 제외(WARN 로그) — 러너 전체·데몬은 계속(FR-3).
- **BR-3 (계정 격리).** baseline 계정 ID가 라이브 LLM 계정 ID와 같으면 그 baseline 제외
  (프로덕션 계정 오염 방지, NFR-1). 빌드 시 1회 검사.
- **BR-4 (스냅샷 정합).** 한 tick에서 baseline 일부가 실패해도 성공한 것 + LLM equity는 기록.
  실패 baseline은 그 tick에 레코드 없음(누락은 `n_points`로 드러남).
- **BR-5 (alpha 정의).** alpha[strategy] = LLM 누적수익 − baseline 누적수익. 양수 = LLM이 그
  기법을 이김. 동일 window(교집합 구간)에서 비교 — 서로 다른 시작 시점은 공통 구간으로 절단.
- **BR-6 (지표 순수성).** `compute_metrics`는 I/O 없음. 입력=시계열 리스트, 출력=지표 객체.
  파일 로드/저장은 별도 함수. (NFR-4 재현성 — 저장된 원천으로 언제든 재산출).

## 3. cadence / buy&hold 정밀화 결정 (Construction 확정)

- **cadence(A2).** 기본 `interval_minutes: "eod"` — 하루 1회(장 마감 후) 전 baseline tick + 스냅샷.
  근거: 결정론 기술전략의 일봉 신호는 분단위 동기화 불필요, 다계정 API 부하(NFR-2)·저장(NFR-3)
  최소. intraday 비교가 필요하면 정수 분(예: 30)으로 override 가능. (NFR Design에서 부하 재확인.)
- **buy&hold 리밸런싱.** 유니버스 신규 편입 종목은 다음 tick에서 BUY(미보유라서 BR-1로 자연 처리).
  편출은 강제 청산하지 않음(보유 지속) — "매수 후 보유"의 순수 정의 유지. 현금 배분은 엔진/리스크의
  기존 사이징에 위임(별도 동일가중 강제 안 함 — 다른 baseline과 동일 사이징 경로로 공정).

## 4. 인터페이스 계약

- `BuyAndHoldStrategy(BaseStrategy)` — 기존 전략과 동일 시그니처. 신규 메서드 없음.
- `BenchmarkRunner.tick() -> None` — 예외를 baseline 단위로 격리, 절대 상위로 전파 안 함(데몬 보호).
- `metrics.compute_metrics(by_strategy: dict[str,list[EquitySnapshot]], llm_key="llm") -> BenchmarkMetrics`.
