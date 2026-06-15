# Track D1 — 죽은 의존성 + 사전 ML 전략 폐기 (Tier 1+2)

> Per-track state. Single writer = this track's worktree session.

## Track Info
- **Track ID**: D1 (first deprecate track)
- **Title**: 죽은 의존성(transformers/quantstats/plotly/matplotlib) + 사전 ML 전략(lstm/rf/base_ml) 폐기
- **Type**: deprecate
- **Status**: merge-awaiting  <!-- Build & Test green 2026-06-14 → /ai-dlc-merge -->
- **Branch**: deprecate/D1
- **Worktree**: .claude/worktrees/D1
- **Base commit**: 1a7645e
- **Start Date**: 2026-06-14T06:43:05Z

## Extension Configuration
- **Security Baseline**: Disabled (N/A) — 코드/의존성 제거, 신규 표면 없음.
- **Property-Based Testing**: Disabled (N/A) — 제거 작업, 신규 로직 없음.

## Scope
Tier 1+2 (사용자 승인). 자세한 내용 [[backtest-deprecation-pending]] 관련.
- **제거**: deps transformers/quantstats/plotly/matplotlib/torch/scikit-learn,
  파일 `src/strategy/ml/{lstm,rf,base_ml}.py`.
- **유지**: `src/strategy/ml/feature_eng.py`(agent+llm formatter 사용), 모든 technical 전략,
  registry/engine/buy_and_hold(F70 벤치마크), 백테스트/strategy.llm(Tier 3, 본 트랙 범위 밖).
- **동반 수정**: main.py import 2줄, strategies.yaml(rf/lstm 정의 + ensemble RF 가중치),
  runtime.py 코드맵 문자열, README/DESIGN 문서.

## Merge Risk Notes
- **공유 파일**: `pyproject.toml`, `main.py`, `config/strategies.yaml`, `README.md`, `docs/DESIGN*.md`,
  `src/agent/steering/runtime.py`. agent.py류 핫스팟 아님.
- **API 변경**: ML 전략 클래스 제거(외부 미노출, 안전).
- **동시 변경 주의**: 없음(예상).

## Stage Progress (deprecate workflow)
- [x] Workspace Detection — brownfield, dead-code 조사 완료
- [x] Stage 1 — Impact Analysis (`inception/deprecate/1-impact.md`)
- [x] Stage 2 — 폐기 결정 게이트 — **즉시 제거** 승인 (2026-06-14)
- [x] Stage 3 — Migration Plan (`inception/deprecate/2-migration.md`)
- [x] Stage 4 — Construction (파일 3개 삭제 + deps 6개 + main/config/runtime/logger/문서 정리)
- [x] Build & Test — 1284 passed / 4 known-unrelated. import OK, 잔존참조 0.
