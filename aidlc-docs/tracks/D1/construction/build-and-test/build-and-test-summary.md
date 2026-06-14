# D1 — Build & Test Summary

**대상**: Tier 1+2 폐기 (죽은 deps + 사전 ML 전략). 즉시 제거.

## 변경/삭제
- **삭제**: `src/strategy/ml/lstm.py`, `rf.py`, `base_ml.py`.
- **`pyproject.toml`**: deps 제거 `transformers`, `quantstats`, `plotly`, `matplotlib`,
  `torch`, `scikit-learn` (6개).
- **`main.py`**: `src.strategy.ml.{rf,lstm}` 등록 import 2줄 제거.
- **`config/strategies.yaml`**: `random_forest`/`lstm` 정의 제거; ensemble에서 RF 제거 +
  가중치 재정규화(ma 0.4 / rsi 0.3 / macd 0.3 = 1.0).
- **`src/agent/steering/runtime.py`**: 코드맵 ml 설명 문자열 갱신(feature_eng 중심).
- **`src/monitoring/logger.py`**: `_NOISY_LOGGERS`에서 `"matplotlib"` 제거.
- **문서**: `README.md`, `docs/DESIGN.md`, `docs/DESIGN_KO.md` ML(RF/LSTM) 언급 정리.
- **유지**: `src/strategy/ml/feature_eng.py` (agent `market.py` + `strategy/llm/data_formatter` 사용).

## 검증 결과 (ALL GREEN — 대상 범위)
- 잔존 참조 sweep: `ml.rf/ml.lstm/base_ml/RandomForestStrategy/LSTMStrategy/BaseMLStrategy/
  torch/sklearn/transformers/quantstats/plotly` → **코드 내 0건**(feature_eng 제외).
- import 스모크: `import main` + `import src.strategy.ml.feature_eng` OK.
- 전체 스위트: **1284 passed, 4 failed**. 4건 모두 D1 무관(선존):
  - `tests/signals/test_sentiment_sweep.py`(3) — base에서도 동일 실패.
  - `tests/test_health_publish.py`(1) — worktree `.env`/`settings.yaml` 부재 환경 아티팩트.
- ML/torch/sklearn 참조 테스트 0건 → 삭제로 깨진 테스트 없음.

## Extension Compliance
- Security Baseline: N/A (코드/의존성 제거).
- Property-Based Testing: N/A (신규 로직 없음).
