# Stage 4 — Implementation summary (speed-review, R2)

작성일: 2026-06-01 · 브랜치 `feat/R2` (worktree `.claude/worktrees/R2`)
모든 변경 **동작 보존**. 특성화 골든 + 전체 스위트 green 유지.

## 측정된 효과 (동일 결과 확인)
| 항목 | 시나리오 | before | after | 배속 | 동치성 |
|------|----------|--------|-------|------|--------|
| C-1a+C-1b 엔진 | MA, 2000 bars | 420 ms | 141 ms | **×3.0** | equity_curve+final_capital 비트 동일 |
| C-2 옵티마이저 | 16 combos × 2000 bars | 2129 ms | 383 ms | **×5.6** | best_params + all_results 동일 |

엔진 배속은 바 수에 비례해 커짐(O(n²)→O(n)). 옵티마이저 배속은 코어 수에 비례.

## 변경 파일
- `src/backtest/optimizer.py` — **C-2**: `ProcessPoolExecutor` 병렬화(모듈레벨 `_run_combo`
  워커). `.map`이 입력(combo) 순서를 보존 → 이후 first-max-wins 선택을 순차로 돌려 결정성 유지.
  실패 combo는 `metric_value=None`로 표식해 스킵(기존 `except: continue` 동일). `max_workers`
  인자 추가(None⇒cpu_count, 1⇒in-process 순차 폴백).
- `src/data/prices.py` (신규) — **C-3p**: `fetch_latest_prices(provider, symbols)` —
  동일 `get_latest_price` 호출을 ThreadPool(≤8)로 동시 실행, per-symbol try/except로 격리
  (실패→None). 단일/빈 심볼은 스레드 없이 그대로.
- `src/risk/exits.py` — **C-3p**: whole-portfolio 가격 갱신 루프를 `fetch_latest_prices`로.
  값·격리 동일(실패 심볼은 갱신 생략).
- `src/agent/equity_log.py` — **C-3p**: `fetch_benchmark`를 `fetch_latest_prices`로. `^` 스트립·
  실패 스킵 동작 동일.
- `src/agent/tools/market.py` — **C-4**: `scoreboard`의 per-symbol fetch+compute를 inner
  `_row()`로 추출 후 `ThreadPoolExecutor.map`(≤8, 순서 보존). 에러 행/순서/값 동일.
- `src/strategy/base.py` — **C-1b 토대**: opt-in capability 추가(`supports_precompute`/
  `precompute`/`generate_signal_at`). 기본값 = 기존 동작(슬라이스+`generate_signal`) → **다른
  전략 전부 불변**.
- `src/strategy/technical/ma_crossover.py` — **C-1b**: precompute(전체 시리즈 rolling MA 1회) +
  `generate_signal_at(i)`(행 인덱싱). 크로스오버 로직은 `_signal()`로 공유 → `generate_signal`과
  동일 출력. rolling mean의 causal성으로 비트 동일.
- `src/backtest/engine.py` — **C-1a+C-1b**: 전략이 precompute 지원 & 비선택형이면 fast-path
  (슬라이스 복사 X, precompute 1회 후 `generate_signal_at(i)`). 그 외엔 기존 경로 100% 유지.

## C-3b 제외 (사용자 결정)
가격 fan-out 단일 배치(`get_bars_multi`)는 latest-price와 값 의미론이 달라질 위험으로 **미진행**.
참고: base의 `get_multiple_bars` 기본 구현은 순차 루프라 진짜 배치도 아님.

## 테스트
- `tests/refactor/scenarios.py` + `golden/baseline.json` — 사전 캡처한 baseline 동작.
- `tests/refactor/test_speed_baseline.py` — 엔진/옵티마이저 골든 + MA fast-path 동치성(바별
  `generate_signal_at(i)==generate_signal(bars[:i+1])`).
- `tests/refactor/test_concurrent_fetch.py` — C-3p/C-4 값·격리·순서 보존.
- 전체: **562 passed** (기존) + refactor 7 = 회귀 없음.

## 미적용(폴백 유지, 동작 불변) — 후속 후보
- rsi/macd/bollinger 기술전략 + ML(`build_technical_features`)은 fast-path 미구현 → 현행
  per-bar 경로(정확하지만 미가속). 필요 시 동일 패턴으로 precompute 추가(각각 골든으로 가드).

## 머지 전 필수
[[feedback-refactor-merge-resweep]] — base `46c48a9` 이후 main 유입 코드를 C-1..C-4 휴리스틱으로
재스윕. C-3p ThreadPool은 Alpaca 공유 client 동시성 → paper read-only 스모크 1회 권장.
