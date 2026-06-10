# R11 Stage 3 — Redesign (목표 구조 + 마이그레이션)

범위: strategy 네이밍 일관화 (all-T1) · 작성일: 2026-06-10

## 목표 구조 / 명명 규칙

**규칙: 디렉터리가 이미 분류하므로 모듈명에서 `_strategy` 접미사 제거.** `llm_strategy`는 stutter라 `strategy`로.
클래스명(`*Strategy`)·`@register_strategy` 키는 **유지**(개명하면 외부 키 호환 깨짐 = 불필요한 T3 위험).

| before | after |
|--------|-------|
| `src/strategy/technical/macd_strategy.py` | `src/strategy/technical/macd.py` |
| `src/strategy/technical/rsi_strategy.py` | `src/strategy/technical/rsi.py` |
| `src/strategy/ml/rf_strategy.py` | `src/strategy/ml/rf.py` |
| `src/strategy/ml/lstm_strategy.py` | `src/strategy/ml/lstm.py` |
| `src/strategy/llm/llm_strategy.py` | `src/strategy/llm/strategy.py` |

유지(이미 정상): `technical/{bollinger,ma_crossover}.py`, `ml/{base_ml,feature_eng}.py`,
`buy_and_hold.py`, `ensemble/{voting,weighted}.py`, `registry.py`, `base.py`.
테스트 파일 `tests/test_strategies.py`는 모듈명과 무관한 묶음 이름이라 그대로(R13 범위도 아님).

## 동치성 논증 (왜 T1인가)
- Python 모듈 = 파일. `git mv`는 정의(클래스/데코레이터/함수) 바이트 동일, 위치만 이동.
- `@register_strategy("macd")` 등 **키는 파일 본문의 리터럴** → 파일명 변경과 무관. registry 룩업·yaml 키 불변.
- import는 `from …macd_strategy import MACDStrategy` → `from …macd import MACDStrategy`로 동일 객체.
- 등록 트리거(`main.py`/`runner.py`/`llm/__init__`/`test`)는 **정적 `import` 문** — 경로만 갱신하면 등록 동작 동일.
- 외부 표면 0(`-m`/동적 import 없음). ∴ 순수 T1.

## 마이그레이션 순서 (작은 단위, 단계마다 green)
1. `git mv` 5개 모듈(위 표).
2. 코드 참조 11곳 갱신: `main.py:92,93,95,96,99`, `src/benchmark/runner.py:20,21`,
   `src/strategy/llm/__init__.py:10`, `tests/test_strategies.py:8,9,130`.
3. 문서 2곳 갱신: `README.md:240`, `docs/DESIGN.md:172`.
4. `rg '_strategy\b' src main.py README.md docs --glob '!aidlc-docs/**'` 로 잔여 확인
   (`register_strategy`/`BaseMLStrategy` 등 정당한 토큰은 제외 — 모듈 경로 `…_strategy` 잔여가 0인지).
5. `pytest tests/test_strategies.py -q` green.
6. import smoke: `python -c "import main; import src.benchmark.runner;
   import src.strategy.technical.macd, src.strategy.technical.rsi, src.strategy.ml.rf,
   src.strategy.ml.lstm, src.strategy.llm.strategy"` (등록 트리거 경로 + 신규 모듈 경로 해석).
7. 전체 스위트 green + `py_compile`.

## 영향 없음 확인
클래스명/키/시그널 로직/yaml 불변. 외부 표면 0 → post-merge-guide 불필요.
