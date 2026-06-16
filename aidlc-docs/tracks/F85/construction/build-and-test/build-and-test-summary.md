# F85 — Build & Test Summary

## 빌드
- 순수 Python, 신규 외부 의존성 없음. `py_compile` 전 변경 모듈 통과.
- `import main` (전체 와이어링 그래프) + `get_settings()` + `_build_risk_manager(...)` 스모크 통과.

## 테스트 실행 (`venv/bin/python -m pytest -q`)
- **전체: 1373 passed**, 31 warnings.
- 신규 `tests/test_aggressiveness.py`: **27 passed** — 포함:
  - resolve fail-safe(파라미터 + hypothesis 임의 문자열), balanced 항등(overlay/disposition 공백)
  - 레벨 단조성(example), overlay allowlist 위반 거부
  - config validator 오타→balanced, Decision 2필드 round-trip + legacy default
  - 리스크 overlay: 3레벨 모두 `shorting_enabled` 불변 + `use_bracket_orders is True` + 사이즈 정확
  - 프롬프트: balanced 바이트 동일, disposition 7빌더 주입, intraday churn 오버라이드
  - 학습: 미성숙 efficacy 제외, per-day 정규화(horizon 비교가능, win_rate 불변), maturity 경계(property)
  - `grade_matured` 멱등(2회=1) + 미성숙/미스탬프 제외
- 회귀 확인(touched 영역): efficacy/quality/recall/self_rewrite/orchestrator/agent/multi_agent/risk/
  short_risk/evals(grading/runner/corpus/scenario) **전부 green**.

## 사전 존재 실패 (F85 무관)
- `tests/signals/test_sentiment_sweep.py` 3건 — **main(f17a36f)에서도 동일 실패** 확인. F77 StockTwits
  sweep persistence; F85가 건드리지 않는 모듈.

## 게이트
Build & Test green → `state.md` Status = `merge-awaiting`. `/ai-dlc-merge` 큐 등록.
