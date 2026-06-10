# R11 Stage 1 — Baseline + 특성화 (strategy 네이밍 일관화)

범위: `strategy/` 모듈 `_strategy` 접미사 제거 + `llm_strategy` stutter 해소 (구조점검 #5)
작성일: 2026-06-09 · Base: `3297de5` · Branch: `refactor/R11` · Worktree: `.claude/worktrees/R11`

## 현재 구조 (접미사 혼용)

| 디렉터리 | 접미사 있음 (개명 대상) | 접미사 없음 (이미 정상, 유지) |
|----------|------------------------|-------------------------------|
| technical/ | `macd_strategy.py`, `rsi_strategy.py` | `bollinger.py`, `ma_crossover.py` |
| ml/ | `rf_strategy.py`, `lstm_strategy.py` | `base_ml.py`, `feature_eng.py` |
| llm/ | `llm_strategy.py` (← stutter `llm.llm_strategy`) | — |
| (top) | — | `buy_and_hold.py`, `base.py`, `registry.py` |
| ensemble/ | — | `voting.py`, `weighted.py` |

## 개명 매핑 (5건)

| before | after | 클래스(불변) | `@register_strategy` 키(불변) |
|--------|-------|--------------|-------------------------------|
| `technical/macd_strategy.py` | `technical/macd.py` | `MACDStrategy` | `"macd"` |
| `technical/rsi_strategy.py` | `technical/rsi.py` | `RSIStrategy` | `"rsi"` |
| `ml/rf_strategy.py` | `ml/rf.py` | `RandomForestStrategy` | `"random_forest"` |
| `ml/lstm_strategy.py` | `ml/lstm.py` | `LSTMStrategy` | `"lstm"` |
| `llm/llm_strategy.py` | `llm/strategy.py` | `LLMStrategy` | `"llm"` |

## 보존해야 할 관측 가능 동작 (외부 계약)

R11은 **모듈 파일명만** 바꾼다. 다음 전부 불변(byte-for-byte):
- 클래스명 5개(`MACDStrategy`/`RSIStrategy`/`RandomForestStrategy`/`LSTMStrategy`/`LLMStrategy`).
- **`@register_strategy` 키**(`"macd"`/`"rsi"`/`"random_forest"`/`"lstm"`/`"llm"`) — 데코레이터 리터럴이라
  **파일명과 decoupled**(R9 critic이 확인한 사실). `config/strategies.yaml`·registry 룩업 키 불변.
- 전략 시그널 로직·파라미터·출력.
- 변경되는 유일한 것: import 경로 `…macd_strategy`→`…macd` 등(코드 식별자, 외부 표면 아님).

## 변경 영향 인벤토리 (전수검사 — repo-wide `rg`, `!aidlc-docs`)

**코드 참조 사이트 (11곳, 6파일):**
- `main.py:92,93,95,96,99` — 전략 등록 트리거 import (rsi/macd/rf/lstm/llm). ※ repo-루트 — R9 critic 교훈으로 포함.
- `src/benchmark/runner.py:20,21` — `_import_baseline_strategies()` 등록 import (macd/rsi).
  ⚠️ **R9 겹침**: R9이 같은 파일 line 10(`config`→`settings`)을 건드림 — **다른 라인(20/21)**이라 머지 자동결합 가능.
- `src/strategy/llm/__init__.py:10` — `from src.strategy.llm.llm_strategy import LLMStrategy` → `llm.strategy`.
- `tests/test_strategies.py:8,9,130` — rsi/macd import + llm 등록 트리거.

**문서 참조 (2곳, 동일 PR 갱신):**
- `README.md:240` — `from src.strategy.ml.rf_strategy import RandomForestStrategy`.
- `docs/DESIGN.md:172` — `llm_strategy.py  LLMStrategy …` 설명.

**외부 표면**: 전략 선택 키는 yaml/registry에 문자열로 있으나 **파일명과 무관**(불변). `python -m …_strategy`
진입점 없음, 동적 import 없음(등록 트리거는 정적 `import` 문). → 순수 T1, post-merge-guide 불필요.

## 특성화 테스트 (before/after green 안전망)

- `tests/test_strategies.py` — 5개 전략 클래스 + registry 룩업 커버. **베이스라인 19 passed** (이 worktree).
- 등록 트리거 경로(`main.py`/`runner.py`/`llm/__init__.py`)는 import 스모크로 보강(테스트 직접 미커버).
- Stage 4 내내 green 유지; red = 동작 변경 신호 → 정지.

## 결론

모듈 개명 5건 + import 11곳 + doc 2곳. 클래스명·registry 키·동작 전부 불변. **all-T1, T3 게이트 없음.**
(R9 critic 교훈: 인벤토리 sweep을 repo-wide로 — `main.py` 등록 import 5곳 포함 확인.)
