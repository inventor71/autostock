# F70 — Application Design (Standard)

> 단일 유닛 `benchmark`. 기존 추상화(BaseStrategy / TradingEngine / BrokerApiBroker / jsonl) 최대 재사용.
> 신규 엔진·신규 브로커 작성 금지 — 조립(composition)만.

## 1. 통합 지점 (검증된 사실)

- **라이브 AI 경로**: `main.run_agent()` → `AgentTradingMode(orchestrator, executor, …).start()`.
  여기서 `broker = create_broker(settings)`, `data_provider`, `universe = resolve_universe(...)`가
  이미 만들어진다. → **섀도우 러너를 여기서 함께 기동**(토글 on일 때).
- **TradingEngine(data_provider, broker, strategies, risk_manager, universe, timeframe, lookback)**
  — baseline 1전략 = 이 엔진 1개 + 전용 계정 브로커. `run_cycle()`이 유니버스 전체를 1회 평가.
- **BrokerApiBroker(api_key, secret_key, account_id, sandbox=True)** — sandbox farm의 계정별 접속.
  생성자에서 계정 검증(`get_trade_account_by_id`) → 부재 시 `BrokerError` (fail-closed 지점).
- **equity 단일 출처**: `broker.get_portfolio_state().equity` (PortfolioState.equity). baseline·LLM
  동일 방식.
- **기록 규약**: `src/core/jsonl.py` `append_record(path, rec)` / `read_records(path, model)`.
- **유니버스**: `resolve_universe(settings, client=…)` → `list[str]`.

## 2. 컴포넌트 모델 (신규)

### C1. `BuyAndHoldStrategy` — `src/strategy/buy_and_hold.py`
- `@register_strategy("buy_and_hold")`, `BaseStrategy` 상속.
- `generate_signal(symbol, bars, portfolio)`: 해당 symbol 포지션이 없으면 `BUY`(confidence 1.0),
  이미 보유 중이면 `HOLD`. → 엔진의 per-symbol 루프가 유니버스 동일가중 1회 매수 후 보유를 구현.
- 의존: 없음(가장 단순한 결정론적 baseline = "시장 동일가중 보유").

### C2. `BenchmarkConfig` — `src/benchmark/config.py`
- 소스: `config/benchmark.yaml` (신규). 필드:
  - `enabled: bool` (마스터 토글, **기본 false** — FR-7/NFR-1 안전)
  - `baselines: list[str]` (기본 `[buy_and_hold, ma_crossover, rsi, macd, bollinger]`)
  - `accounts: dict[str,str]` (전략명 → sandbox account_id)
  - `interval_minutes: int | "eod"` (cadence — NFR 단계 확정; 기본 보수적)
  - `storage_dir: str` (기본 `data/benchmark`)
  - `retention_days: int`
- `from_settings(settings)` 로더 + 검증(미지정 baseline·계정 누락 경고).

### C3. `BenchmarkRunner` — `src/benchmark/runner.py`
- 생성자: `(config, data_provider, risk_config, universe, timeframe, llm_portfolio_provider)`.
  - `data_provider`는 **라이브와 공유**(중복 시장데이터 fetch 회피 → NFR-2).
  - `llm_portfolio_provider = broker.get_portfolio_state` (라이브 계정 equity 동시 기록).
- `build()`: baseline마다 `BrokerApiBroker(account_id=map[name])` + `create_strategy(name)` +
  `TradingEngine(...)` 조립. **fail-closed**: 계정 매핑 누락/`BrokerError` → 해당 baseline 스킵
  + 경고 로그, 나머지는 계속(FR-3, NFR-1).
- `tick()`: 활성 baseline 엔진마다 `engine.run_cycle()` 실행 → 각 계정 equity 스냅샷 +
  `llm_portfolio_provider()` equity 스냅샷을 `EquityRecorder`로 기록. 예외는 baseline 단위 격리.
- `start()/stop()`: 백그라운드 스레드 + 인터벌 스케줄러(`interval_minutes`/EOD). 토글 off면 no-op.

### C4. `EquityRecorder` — `src/benchmark/store.py`
- `record(strategy_name, portfolio_state, ts)` → `data/benchmark/equity/<strategy>.jsonl` append.
- 레코드 스키마(`EquitySnapshot` pydantic): `{ts, strategy, account_masked, equity, cash, position_count}`.
- `append_record` 재사용. append-only, 보존정책은 별도 청소 유틸(또는 retention_days 기반).

### C5. `metrics` — `src/benchmark/metrics.py` (순수 함수 + CLI)
- `load_series(storage_dir, strategy) -> list[EquitySnapshot]`.
- `compute_metrics(series_by_strategy, llm_series) -> BenchmarkMetrics`: 전략별 누적수익률,
  **alpha = LLM누적 − baseline누적**, 변동성, MDD, Sharpe. **순수**(I/O 분리 → NFR-4 재현성).
- `persist(metrics, storage_dir)` → `data/benchmark/metrics/<ISO>.jsonl` 스냅샷.
- CLI 진입: `python -m src.benchmark.metrics`(저장된 시계열로 오프라인 재계산 — D3 "나중에 정량
  지표 추출" 충족).

### C6. 와이어링 — `main.run_agent()` (+ 선택적으로 `run_paper()`)
- `BenchmarkConfig.from_settings(settings)` → `enabled`면 `BenchmarkRunner(...).start()`,
  데몬 종료 시 `stop()`. **agent 모드 코드 흐름은 토글 off일 때 완전 불변**(무영향).

## 3. 데이터 플로우 (ASCII)

```text
                 resolve_universe(settings) ── universe ─┐
 create_broker(settings) ─ broker(LLM 계정) ─ get_portfolio_state ─┐  │
 create_data_provider ───── data_provider ──(공유)──┐               │  │
                                                    v               v  v
   config/benchmark.yaml ─> BenchmarkConfig ─> BenchmarkRunner.build()
                                                    │
          ┌──────────── per baseline (fail-closed) ─┴───────────────┐
          v                                                         v
   BrokerApiBroker(acct_A)                                BrokerApiBroker(acct_E)
   TradingEngine(buy_and_hold)        …(5개)…             TradingEngine(bollinger)
          │ run_cycle()                                        │ run_cycle()
          v                                                    v
        equity ──────────────► EquityRecorder ◄──────────── equity
                                    │  + LLM equity (llm_portfolio_provider)
                                    v
                      data/benchmark/equity/<strategy>.jsonl  (원천 시계열)
                                    │
                       metrics.compute (순수) ── persist ──► data/benchmark/metrics/<ts>.jsonl
                                    ▲
                       CLI: python -m src.benchmark.metrics (오프라인 재계산)
```

## 4. 설계 결정 / 근거

- **D-A. 병렬 러너 vs 데몬 틱.** baseline은 결정론적이라 LLM의 turn 구조와 동기화할 필요 없음 —
  필요한 건 *동일 유니버스·동일 wall-clock 구간·동일 시작자본*뿐. 따라서 자체 인터벌 스케줄러를
  가진 백그라운드 러너로 분리(낮은 결합, "항상 켜둠" 단순). 데몬은 start/stop만 호출.
- **D-B. data_provider 공유.** baseline들이 시장데이터를 중복 fetch하면 rate-limit/지연(NFR-2).
  읽기 전용이므로 라이브 인스턴스 재사용.
- **D-C. 동일 RiskManager 설정.** 전략 대 전략 비교가 되도록 baseline도 라이브와 동일 risk config
  사용(단, bracket order는 결정론 전략이 레벨을 안 주므로 비적용 — 상세는 Functional/NFR).
- **D-D. 계정 격리 = 프로덕션 무영향(NFR-1).** baseline은 오직 `accounts` 맵의 sandbox 계정에만
  주문. LLM 계정 ID와 교차 금지 — `build()`에서 LLM `broker_account_id`와 충돌 검사(겹치면 그
  baseline fail-closed).
- **D-E. 원천/파생 분리(NFR-4).** equity 시계열(원천)과 지표(파생)를 다른 파일에 저장 → 지표
  공식이 바뀌어도 과거 재산출.

## 5. 미해결 → Construction에서 확정

- **계정 수급(A1)**: sandbox farm에 baseline 5개분 계정 확보 여부 → 부족 시
  `scripts/broker_create_accounts.py` 증설. (가상 서브포트폴리오 차선책은 보류 — 사용자가 "실제
  페이퍼 계정 섀도우" 선택했으므로 실계정 우선.)
- **cadence(A2)**: `interval_minutes` 기본값 / EOD 1회 down-sample 여부 → NFR Design.
- **보존정책**: `retention_days` 적용 방식(청소 잡 vs 무한) → NFR Design.
- **buy&hold 리밸런싱**: 신규 유니버스 편입 종목 매수 시점/현금 배분 정밀화 → Functional Design.

## 6. 영향 파일 요약

| 파일 | 변경 |
|------|------|
| `src/strategy/buy_and_hold.py` | 신규 (C1) |
| `src/strategy/registry.py` 임포트 | buy&hold 등록 트리거(필요 시) |
| `src/benchmark/{__init__,config,runner,store,metrics}.py` | 신규 (C2~C5) |
| `config/benchmark.yaml` | 신규 (C2) |
| `main.py` `run_agent` (+`run_paper`) | 러너 start/stop 훅 (C6, 토글 가드) |
| `data/benchmark/` | 신규 저장(gitignore 확인) |
| `config/config.py` settings | `benchmark` 설정 섹션 추가 |
