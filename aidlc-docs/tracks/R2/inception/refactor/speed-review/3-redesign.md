# Stage 3 — Redesign: 목표 구조 + 동치성 논증 (speed-review, R2)

작성일: 2026-06-01
구현 범위(Stage 2 확정): **C-1a, C-1b, C-2, C-3p, C-4** (C-3b 제외).
원칙: 각 항목은 Stage 1 특성화 골든이 **before/after green**을 유지해야 한다. red = T3 신호 → 정지.

---

## 0. 공통: 특성화 골든 (구현 전 먼저 작성)

`tests/refactor/test_speed_baseline.py` (worktree `feat/R2`):
- **G-engine**: 고정 `bars`(시드된 합성 OHLCV) + 고정 전략(RSI 등) + 고정 risk_config →
  `BacktestResult`의 `equity_curve`(리스트), `round_trips`, 핵심 metrics를 캡처해 JSON 골든으로
  저장하고 비교. **부동소수 비교는 `==`(비트 동일) 우선**, C-1b가 불가피하게 어긋나면
  `pytest.approx(rel=1e-9)`로 낮추되 그 사실을 사용자에게 보고(승인 조건).
- **G-opt**: 고정 grid + bars → `(best_params, [r['metric_value'] for r in all_results])` 캡처.
  병렬 전후 **best_params 동일 + all_results 집합 동일 + 순서 결정성** 검증.
- **G-exits**: `run_polled_exits`를 다심볼 포트폴리오 + 1개 심볼 강제-실패(provider mock)로
  호출 → 발동 주문 집합과 best-effort 격리(나머지 심볼 정상 갱신) 동일.
- **G-scoreboard**: 고정 symbols + 합성 provider → `scoreboard()` 반환 리스트 동일(값·순서).

---

## C-1 백테스트 엔진 (engine.py)

### 동치성 핵심 (왜 동작 보존인가)
`build_technical_features`와 기술전략(rsi/macd/bollinger/ma)의 지표는 **전부 causal/rolling**이다:
RSI(Wilder), MACD(`ewm`), Bollinger(rolling mean/std), SMA(rolling), ATR. 위치 `i`의 값은
**오직 `data[0:i]`에만 의존**하고 미래 바를 보지 않는다. 따라서
```
build(full_bars).iloc_at(ts_i)  ==  build(full_bars[:i+1]).iloc[-1]
```
즉 **전체 시리즈로 한 번 계산해 행 i를 읽는 것**과 **매 바 잘라 재계산하는 것**이 수학적으로
동일하다. 현행 per-bar 재계산은 순수 낭비(O(n²)). (라벨 매핑은 positional이 아니라
**DatetimeIndex 라벨**로 해 `dropna` 정렬 차이를 흡수한다.)

### C-1a — 슬라이스 복사 절감 (T1)
- 현행: 매 바 모든 심볼에 `market_data[symbol] = symbol_bars.iloc[:i+1]`(복사).
- 변경: 가격 전진 루프의 `row = symbol_bars.iloc[i]`는 그대로(O(1)). 아래 C-1b fast-path를
  쓰는 전략에는 슬라이스를 만들지 않는다. fallback 전략에는 현행 슬라이스 유지(동작 불변).

### C-1b — precompute-once fast-path (사용자 승인, opt-in superset)
- **엔진에 opt-in 경로 추가(추가형/superset)**: 전략이 새 capability를 구현하면
  `precompute(full_bars)` 1회 → 매 바 `generate_signal_at(i)`(행 인덱싱) 호출. 미구현 전략은
  **현행 `generate_signal(symbol, history, portfolio)` 경로 그대로**(behavior 불변 = 해당 전략엔 T1).
- 적용 대상(이득 큰 곳): 기술전략(rsi/macd/bollinger/ma_crossover) + ML(`build_technical_features`).
  각 전략의 precompute는 인라인 지표를 **전체 시리즈로 1회 계산**해 보관, `_at(i)`는 행 읽기.
- **가드**: G-engine 골든. 비트 동일이면 그대로, 어긋나면 허용오차 범위를 사용자 보고 후 확정.
- select_symbols 입력: fast-path에서도 selection이 필요로 하는 최소 데이터(현재가/지표 행)를
  인덱싱으로 제공 — full-slice 복사 제거.

---

## C-2 옵티마이저 병렬화 (optimizer.py) — T1

- `for combo in combinations` → `ProcessPoolExecutor`(기본 `max_workers=os.cpu_count()`,
  설정 가능). 각 워커: `(strategy_class, params, symbol, bars, risk_config, initial_capital,
  metric)` 받아 엔진 1회 실행 후 `(params, metric_value, result)` 반환.
- **결정성 보존(핵심)**: 워커 결과를 **원래 combo 순서로 재정렬**한 뒤 현행과 동일한
  `for ... if metric_value > best_metric_value`(strict `>`, **first-max-wins**) 선택 루프를
  순차로 돈다. → tie-break·best 선택이 순차판과 비트 동일.
- 피클 주의: `self._logger`(loguru) 비전달 — 워커는 자체 로깅/무로깅. `bars`(DataFrame)는
  피클 전송(또는 워커가 재로딩). 실패한 combo는 현행처럼 스킵(예외 삼킴 동작 보존).
- 폴백: `max_workers=1`이면 순차와 동일 경로(작은 grid·디버그용).

---

## C-3p 데몬 가격 fetch 병렬화 (값 보존) — T1

- 대상: `risk/exits.py`의 whole-portfolio `for sym: get_latest_price(sym)` 루프,
  `equity_log.fetch_benchmark`의 per-symbol 루프.
- 변경: **동일한 `get_latest_price(sym)` 호출**을 `ThreadPoolExecutor`(bounded, 예:
  `min(8, len(symbols))`)로 동시 실행. 반환값·할당 대상은 그대로 → **값 불변**.
- best-effort 격리 보존: 각 future를 개별 try/except로 감싸 **1개 심볼 실패가 나머지를
  안 죽인다**(현행 except-pass와 동일). 부분 실패 시 성공분만 갱신.
- **검증 항목(thread-safety)**: Alpaca `StockHistoricalDataClient`(공유 requests.Session)에
  대한 동시 호출 안전성 확인. 호출별 request 객체는 독립이라 공유 가변상태는 세션뿐 —
  bounded 풀로 제한하고, 불안하면 심볼당 호출만 동시화(세션은 requests의 thread-safe
  사용 범위 내). G-exits 골든 + 라이브 paper read-only 스모크로 확인.

---

## C-4 scoreboard fetch 병렬화 — T1

- `agent/tools/market.py::scoreboard`의 `for symbol: provider.get_bars(symbol, limit)` →
  `ThreadPoolExecutor.map`로 동시 fetch. **결과 행의 순서는 입력 symbols 순서로 보존**,
  per-symbol 예외 격리(현행 "한 심볼 실패가 스캔을 안 가라앉힘") 유지.
- cold CLI(`python -m src.agent.tools scoreboard`)에서 새 provider라 세션 공유 우려 적음.
- 가드: G-scoreboard 골든(반환 리스트 값·순서 동일).

---

## 마이그레이션 순서 (작은 단위, 단계마다 골든 green)

1. **골든 먼저**: G-engine / G-opt / G-exits / G-scoreboard 작성·green(현행 캡처).
2. **C-2**(옵티마이저) — 위험 최저, 골든 G-opt로 즉시 검증.
3. **C-3p**(가격 fetch 병렬) — G-exits + paper read-only 스모크.
4. **C-4**(scoreboard) — G-scoreboard.
5. **C-1a**(슬라이스 복사 절감) — G-engine.
6. **C-1b**(precompute fast-path) — 전략별로 추가, **각 전략마다 G-engine 재실행**. red면
   정지·허용오차 사용자 보고.
7. 전체 회귀: `pytest` + 기존 백테스트/리스크 테스트.
8. **머지 직전 재스윕**(R2 state.md 지시 / [[feedback-refactor-merge-resweep]]): base
   `46c48a9` 이후 main에 들어온 코드를 C-1..C-4 휴리스틱으로 재diff.

## 보존 불변식 재확인 (Stage 1 §B 연계)
주문 단일 게이트·CommandBus 직렬화·best-effort 격리·BacktestResult 동치·옵티마이저
first-max-wins — 전부 위 설계에서 명시적으로 보존. 신규 동작 변경 없음(C-1b만 골든으로
동치성 실측 확인, 어긋날 시 사용자 승인).
