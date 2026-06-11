# R8 Stage 3 — Redesign (목표 구조 + 마이그레이션)

범위: `src/agent/` 재구조화 (T1 + 기승인 `-m` 클린브레이크) · 작성일: 2026-06-11

## 목표 구조

```
src/agent/
  __init__.py
  orchestrator.py  session.py  executor.py  journal.py  prompts.py   # 코어 루프 — 불변
  reports.py                       # ← agent_reports.py (stutter 해소)
  logs/                            # 텔레메트리/장부
    __init__.py (docstring만, 재export 없음)
    equity.py   ← equity_log.py    (__main__ 유지; -m 경로만 변경)
    trades.py   ← trades_log.py
    turn.py     ← turn_log.py
  learning/                        # 자가학습 스택 (F62/F64/F65)
    __init__.py (docstring만)
    efficacy.py  recall.py  self_rewrite.py  constitution.py  review.py
  intraday/  quality/  steering/  tools/  templates/   # 기존 서브패키지 — 불변
```

명명 규칙: 디렉터리(`logs/`)가 분류하므로 `_log` 접미사 제거(`equity_log`→`logs/equity`) — R11의
`_strategy` 제거와 동일 원칙. `learning/`은 파일명 그대로(이미 무접미사). 코어 5파일은 최상위 유지
(가장 hot한 진입점 — 불필요한 churn 회피).

## 동치성 논증
- `git mv` = 정의 byte 동일(특히 `AGENT_CONSTITUTION` — `test_constitution_pin`이 내용 고정 검증).
- 데이터 산출 경로(JSONL/CSV)는 모듈 내 경로 상수/인자로 결정 — 모듈 위치와 무관, 불변.
- `__init__.py`는 docstring만(재export shim 없음) — 호출부 ~50곳 직접 갱신.
- 문자열 monkeypatch·모듈객체 import는 전수검사로 특정, 명시 갱신(ledger #5·#6).
- `-m` 진입점은 기승인 클린브레이크(non-src 참조 0).

## 마이그레이션 순서 (단계마다 green)
1. `mkdir logs learning` + 빈(docstring) `__init__.py` 2개.
2. `git mv` ×9 (logs 3 + learning 5 + reports 1).
3. 일반 import 일괄 치환(파일 단위 `rg -l` → sed):
   `agent.equity_log`→`agent.logs.equity`, `agent.trades_log`→`agent.logs.trades`,
   `agent.turn_log`→`agent.logs.turn`, `agent.efficacy`→`agent.learning.efficacy`,
   `agent.recall`→`agent.learning.recall`, `agent.self_rewrite`→`agent.learning.self_rewrite`,
   `agent.constitution`→`agent.learning.constitution`, `agent.review`→`agent.learning.review`,
   `agent.agent_reports`→`agent.reports`.
   (문자열 monkeypatch도 같은 패턴이라 함께 잡힘 — 치환 후 7곳 개별 확인.)
4. 모듈-객체 import 명시 처리: `orchestrator.py:334,546` `from src.agent import agent_reports` →
   `from src.agent import reports` + 본문 `agent_reports.`→`reports.` (해당 함수 스코프 한정).
5. `docs/DESIGN.md:310` 갱신.
6. 잔여 0 확인: `rg 'agent\.(equity_log|trades_log|turn_log|efficacy|recall|self_rewrite|constitution|review|agent_reports)|agent import (equity_log|trades_log|turn_log|efficacy|recall|self_rewrite|constitution|review|agent_reports)' --glob '!aidlc-docs/**'`
   ※ `agent.learning.efficacy` 같은 새 경로가 `agent\.efficacy`에 오매칭되지 않도록 단어경계 확인.
7. 검증: agent 테스트(158) → `python -m src.agent.logs.equity --help 또는 import` 스모크 →
   전체 스위트 + py_compile.
8. post-merge-guide: `-m` 경로 변경 1줄(클린브레이크) + 데몬 재시작 노트.

## 영향 없음 확인
공개 함수 시그니처·헌장 내용·데이터 경로·스키마 전부 불변. 코어 5파일 무변경.
