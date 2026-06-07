# F70 / benchmark — Code Generation Plan

> worktree `.claude/worktrees/F70` (feat/F70). 단일 유닛. 신규 엔진/브로커 없음 — 조립.

## 신규 파일
- [x] `src/strategy/buy_and_hold.py` — `@register_strategy("buy_and_hold")` BuyAndHoldStrategy (BR-1)
- [x] `src/benchmark/__init__.py`
- [x] `src/benchmark/models.py` — EquitySnapshot / BaselineMetric / BenchmarkMetrics (pydantic)
- [x] `src/benchmark/config.py` — BenchmarkConfig.from_settings (토글/baselines/accounts/cadence/저장/보존)
- [x] `src/benchmark/store.py` — EquityRecorder (jsonl append) + read + retention 컴팩션
- [x] `src/benchmark/metrics.py` — compute_metrics(순수) + load/persist + `__main__` CLI
- [x] `src/benchmark/runner.py` — BenchmarkRunner (build/tick/start/stop, fail-closed, data_provider 공유)

## 기존 파일 수정 (최소)
- [x] `config/config.py` — Settings에 `benchmark: dict = {}` 추가
- [x] `config/settings.yaml` — `benchmark:` 섹션 (enabled=false 기본)
- [x] `config/strategies.yaml` — `buy_and_hold` 전략 정의 추가(params 없음)
- [x] `main.py` `run_agent` — 토글 on이면 BenchmarkRunner start, 종료 시 stop (가드)
- [x] `.gitignore` — `data/benchmark/`

## 테스트 (tests/benchmark/)
- [x] `test_buy_and_hold.py` — 미보유→BUY, 보유→HOLD, 빈 bars→InsufficientDataError
- [x] `test_config.py` — 파싱/기본값/누락 경고
- [x] `test_store.py` — append→read 라운드트립, account_masked만(시크릿 없음), retention 컴팩션
- [x] `test_metrics.py` — compute 순수성(동일입력=동일출력), alpha 정의, 공통 window 절단, MDD/Sharpe edge
- [x] `test_runner.py` — 계정충돌 제외(BR-3), 매핑누락 fail-closed(BR-2), toggle off no-op, tick 예외격리(BR-4), data_provider 공유(중복 fetch 없음)

## 검증
- [x] typecheck/lint (해당 시) + `pytest tests/benchmark -q`
- [x] toggle off일 때 import/agent 경로 무영향 스모크
