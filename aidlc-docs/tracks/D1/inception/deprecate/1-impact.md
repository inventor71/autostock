# D1 — 영향 분석 (Impact Analysis)

**범위**: Tier 1 (죽은 의존성) + Tier 2 (사전 ML 전략) — 사용자 승인 2026-06-14.
**원칙**: 죽은 코드/의존성 제거. 외부 계약 없음 → 거의 behavior-preserving.

## 무엇을 폐기하나

### Tier 1 — 죽은 의존성 (pyproject.toml `dependencies`)
| 의존성 | 코드 참조 | 판정 |
|---|---|---|
| `transformers>=4.35.0` | **0건** | 완전 미사용 |
| `quantstats>=0.0.62` | **0건** | 완전 미사용 |
| `plotly>=5.18.0` | **0건** | 완전 미사용 |
| `matplotlib>=3.8.0` | `src/monitoring/logger.py:46` 의 침묵-로거 **문자열 1개**뿐(라이브러리 import 없음) | 사실상 미사용 |
| `torch>=2.0.0` | `src/strategy/ml/lstm.py`만 | Tier 2 제거 후 무참조 |
| `scikit-learn>=1.3.0` | `src/strategy/ml/rf.py`만 | Tier 2 제거 후 무참조 |

### Tier 2 — 사전(pre-agent) ML 전략 파일
| 파일 | 끌어오는 의존성 | 유일 참조 |
|---|---|---|
| `src/strategy/ml/lstm.py` (`LSTMStrategy`) | torch | `main.py:101` 등록 import + strategies.yaml |
| `src/strategy/ml/rf.py` (`RandomForestStrategy`) | scikit-learn | `main.py:100` 등록 import + strategies.yaml |
| `src/strategy/ml/base_ml.py` (`BaseMLStrategy`) | — | 위 두 파일만 상속 |

**유지(중요)**: `src/strategy/ml/feature_eng.py` — `build_technical_features`를 `src/agent/tools/market.py`
와 `src/strategy/llm/data_formatter.py`가 사용. **삭제 금지.** `src/strategy/ml/` 디렉터리는
`feature_eng.py` + `__init__.py`만 남김.

## 누가 쓰나 (호출부 전수조사)
- **내부 사용처**: 위 표가 전부. ML 전략 클래스를 이름으로 조회하는 라이브 경로 없음
  (F70 벤치마크는 technical + buy&hold만 측정자로 사용, agent는 ML 전략 미사용).
- **레지스트리**: `@register_strategy` 데코레이터는 import 시점에만 등록 → 파일+main.py import
  제거 시 자동으로 레지스트리에서 사라짐. 이름 조회하는 코드 없음.
- **테스트**: ML/torch/sklearn/lstm/rf 참조 테스트 **0건** (`tests/` grep 결과 없음). 깨지는 테스트 없음.
- **외부 계약**: 없음. CLI 플래그/공개 API/저장 포맷에 ML 전략 노출 없음
  (model_path `./models/*.pkl|*.pt`는 생성된 적 없는 산출물 경로일 뿐).

## 동반 수정 필요 (제거의 직접 결과)
1. `main.py:100-101` — `import src.strategy.ml.rf` / `import src.strategy.ml.lstm` 제거.
2. `config/strategies.yaml`:
   - `strategies.random_forest`, `strategies.lstm` 정의 블록 제거.
   - `ensemble.strategies`에서 `random_forest`(weight 0.3) 항목 제거 → 남은 가중치
     (ma 0.3 / rsi 0.2 / macd 0.2 = 0.7) 재정규화(예: ma 0.4 / rsi 0.3 / macd 0.3 = 1.0).
     > ensemble은 active_strategies(=[llm])에 없어 라이브 미사용이나, 댕글링 참조 제거 위해 정리.
3. `src/agent/steering/runtime.py:530` — 코드맵 설명 문자열
   `"src/strategy/ml": "ML strategies — Random Forest, LSTM"` →
   `"src/strategy/ml": "ML feature engineering (technical features for agent/LLM)"`로 갱신.
4. 문서: `README.md:97`, `docs/DESIGN.md:190`, `docs/DESIGN_KO.md:163` — ML(RF/LSTM) 언급 제거,
   `feature_eng.py`만 남김.
5. `matplotlib` 침묵-로거 문자열(`src/monitoring/logger.py:46`) — 의존성 제거에 맞춰 정리(선택; 무해).

## 왜 폐기하나 (복잡도 비용)
- **설치/이미지 비용**: torch + transformers는 수백 MB~GB. 한 번도 안 쓰는데 모든 환경
  (venv, docker-verify 이미지, CI)이 이를 설치/캐시. transformers/quantstats/plotly는 0 참조.
- **인지 비용**: "ML 전략이 있다"는 착시 — 실제로는 죽은 경로. 코드맵·문서·config가 이를 광고.
- **유지 비용**: torch/sklearn API 변경 시 깨질 표면적(실익 0).

## 무엇을 잃나
- LSTM/RandomForest 전략으로 백테스트/페이퍼 트레이딩하는 능력. **현재 라이브 미사용**이며
  agent(LLM PM) + F70 technical baseline이 트레이딩/측정을 담당하므로 실질 손실 없음.
- 되살리려면 git 히스토리에서 복원 가능(파일 3개 + deps).

## 리스크 / 검증
- 리스크 **낮음**: 죽은 코드/deps 제거. 깨지는 테스트·호출부 없음.
- 검증: 제거 후 전체 테스트 green, `python -c "import main"` import OK,
  `python main.py --mode paper`(클래식 경로)가 llm/technical 전략으로 정상 기동(rf/lstm 미참조),
  `pip install -e .` 재설치로 torch/transformers 미설치 확인.
