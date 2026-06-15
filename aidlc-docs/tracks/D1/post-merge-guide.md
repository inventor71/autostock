# D1 — Post-Merge Note (죽은 코드/의존성 폐기)

순수 내부 제거(런타임 동작 변경 없음)라 정식 post-merge-guide는 대부분 N/A. 단, **환경 정리**
한 가지만 관측 가능:

## 머지 후 권장 조치 (선택)
- 기존 venv에는 아직 `torch`/`transformers`/`scikit-learn`/`quantstats`/`plotly`/`matplotlib`이
  설치돼 있음(이번 변경은 pyproject에서 의존성만 뺌). 디스크/이미지 정리를 원하면 재설치:
  ```bash
  pip install -e .            # 새 의존성 세트로 정합화 (heavy deps는 더 이상 요구 안 함)
  # 공간 회수까지 원하면:
  pip uninstall -y torch transformers scikit-learn quantstats plotly matplotlib
  ```
- docker-verify / CI 이미지: 다음 빌드부터 위 패키지를 더 이상 설치하지 않음 → 이미지 축소.

## 동작 영향
- 없음. 제거된 ML 전략(LSTM/RandomForest)은 라이브 미사용이었고, agent(LLM PM) + F70
  technical baseline이 트레이딩/측정을 담당. 클래식 paper/backtest 경로도 ML 없이 정상
  (active_strategies=[llm], ensemble은 technical만).

## 롤백
- git revert (파일 3개 + deps + config/문서). 모델 산출물(`./models/*`)은 존재한 적 없음.

## 범위 밖 (후속 후보)
- Tier 3 (사전 LLM 경로 `src/strategy/llm/` + `src/backtest/` + 클래식 CLI 모드) — 별도 트랙.
