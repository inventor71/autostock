# Tier Ledger — R11 strategy 네이밍 일관화

범위: `strategy/` `_strategy` 접미사 제거 5건 + `llm_strategy` stutter (구조점검 #5)
작성일: 2026-06-10

## T1 — 동작 보존 (자율 진행)
| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| 1 | `technical/macd_strategy.py` → `technical/macd.py` (`git mv`) | `MACDStrategy`/키 `"macd"` 동일 | `tests/test_strategies.py` (green) | 클래스/키 불변, 위치만 |
| 2 | `technical/rsi_strategy.py` → `technical/rsi.py` | `RSIStrategy`/`"rsi"` | 동상 | 동상 |
| 3 | `ml/rf_strategy.py` → `ml/rf.py` | `RandomForestStrategy`/`"random_forest"` | test_strategies + import smoke | 동상 |
| 4 | `ml/lstm_strategy.py` → `ml/lstm.py` | `LSTMStrategy`/`"lstm"` | import smoke | 동상 |
| 5 | `llm/llm_strategy.py` → `llm/strategy.py` (stutter 해소) | `LLMStrategy`/`"llm"` | test_strategies(등록 트리거) | 동상 |
| 6 | 참조 11곳 + 문서 2곳 `…_strategy`→`…` 갱신 | import 결과 동일 객체 | 위 테스트 + import smoke | Python 모듈=파일 |

## T2 — 안전한 확장
없음.

## T3 — 의도 변경 / 기능 cut (🛑)
없음. — `@register_strategy` 키(`"macd"`/`"rsi"`/`"random_forest"`/`"lstm"`/`"llm"`)는 데코레이터 리터럴로
파일명과 decoupled → `config/strategies.yaml`·registry 룩업 불변. 클래스명 불변. 외부 표면 0(`-m`/동적 import 없음).

## 정지 지점
- [x] T3 항목 없음 — 게이트 불필요
- [x] 모든 T1 항목이 기존 `test_strategies.py` + import smoke로 보호됨

## 참조 사이트 (전수, repo-wide — `!aidlc-docs`)
코드(11): `main.py:92,93,95,96,99`; `src/benchmark/runner.py:20,21`(R9와 다른 라인); `src/strategy/llm/__init__.py:10`;
`tests/test_strategies.py:8,9,130`
docs(2): `README.md:240`, `docs/DESIGN.md:172`
