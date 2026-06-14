# D1 — Migration Plan (즉시 제거)

**방식**: 즉시 제거 (사용자 승인 2026-06-14). 외부 계약 없음 → 유예/대체재 불필요.
각 단계 후 테스트 green 유지. 한 커밋으로 묶되 호출부·문서·config·deps를 함께 정리.

## 제거 순서
1. **ML 전략 파일 삭제**: `src/strategy/ml/lstm.py`, `rf.py`, `base_ml.py`.
   (`feature_eng.py`, `__init__.py` 유지.)
2. **`main.py`**: `import src.strategy.ml.rf` / `import src.strategy.ml.lstm` 2줄 제거.
3. **`config/strategies.yaml`**:
   - `strategies.random_forest`, `strategies.lstm` 블록 제거.
   - `ensemble.strategies`에서 `random_forest` 제거 + 가중치 재정규화
     (ma 0.3→0.4 / rsi 0.2→0.3 / macd 0.2→0.3, 합 1.0).
4. **`src/agent/steering/runtime.py`**: 코드맵 문자열 ml 설명 → feature-eng 중심으로 갱신.
5. **`src/monitoring/logger.py`**: `_NOISY_LOGGERS`에서 `"matplotlib"` 제거(라이브러리 제거 동반).
6. **`pyproject.toml`** deps 제거: `transformers`, `quantstats`, `plotly`, `matplotlib`,
   `torch`, `scikit-learn`.
7. **문서**: `README.md`, `docs/DESIGN.md`, `docs/DESIGN_KO.md`의 ML(RF/LSTM) 언급 정리
   (`feature_eng`만 남김).

## 죽는 테스트 처리
- 없음. ML/torch/sklearn 참조 테스트 0건 → 삭제/교체할 테스트 없음.

## 검증
- 전체 `pytest` green (회귀 없음).
- `python -c "import main"` + `python main.py --help` import OK.
- 클래식 paper 경로가 ml 미참조로 정상(레지스트리에 rf/lstm 없어도 active=[llm]만 로드).
- `pip install -e . --dry-run` 또는 재설치로 torch/transformers 미설치 확인(선택).

## 롤백
- git revert (파일 3개 + deps + config/문서). 모델 산출물(`./models/*`)은 존재한 적 없음.
