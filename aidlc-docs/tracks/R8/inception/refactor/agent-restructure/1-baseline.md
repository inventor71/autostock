# R8 Stage 1 — Baseline + 특성화 (`src/agent/` 재구조화)

범위: agent 최상위 grab-bag 15파일 → `logs/`·`learning/` 서브패키지 + `agent_reports` stutter (구조점검 #1)
작성일: 2026-06-11 · Base: `76ff7b6` (R9–R12 머지 후 main) · Branch: `refactor/R8` · Worktree: `.claude/worktrees/R8`

## 이동 매핑 (9모듈)

| before (src/agent/) | after | 비고 |
|---------------------|-------|------|
| `equity_log.py` | `logs/equity.py` | `__main__` 진입점 보유(:113) — `-m` 경로 클린브레이크(기결정) |
| `trades_log.py` | `logs/trades.py` | |
| `turn_log.py` | `logs/turn.py` | |
| `efficacy.py` | `learning/efficacy.py` | |
| `recall.py` | `learning/recall.py` | |
| `self_rewrite.py` | `learning/self_rewrite.py` | 문자열 monkeypatch ×6 (`test_orchestrator_selflearning.py`) |
| `constitution.py` | `learning/constitution.py` | 불변 헌장 — 내용 byte 불변 필수 |
| `review.py` | `learning/review.py` | |
| `agent_reports.py` | `reports.py` | stutter 해소; `from src.agent import agent_reports`(모듈 객체 import, orchestrator:334,546) + 문자열 monkeypatch(:199) |

**유지(최상위, hot 코어 루프):** `orchestrator.py` `session.py` `executor.py` `journal.py` `prompts.py`
`__init__.py` + `intraday/` `quality/` `steering/` `tools/` `templates/` 서브패키지.

## 변경 영향 인벤토리 (전수 — repo-wide `rg`, `!aidlc-docs`)

참조 합계 ~50곳. 유형별:
- **일반 import** (`from src.agent.X import …` / `import src.agent.X`): equity_log 7 · trades_log 4 ·
  turn_log 10 · efficacy 6 · recall 3 · self_rewrite 10 · constitution 3 · review 3 · agent_reports 4
  (src: orchestrator/executor/journal/steering 등 + tests 다수 — Stage 4에서 `rg -l` 파일 단위 일괄 치환)
- **모듈-객체 import**: `orchestrator.py:334,546` `from src.agent import agent_reports` → `import reports` 필요
  (지연 import; 모듈명 자체가 바뀌는 유일 케이스 — 단순 경로 치환으론 안 잡힘, 명시 처리)
- **문자열 monkeypatch (7곳)**: `test_agent_reports.py:199`(`"src.agent.agent_reports.os.replace"`),
  `test_orchestrator_selflearning.py:53,56,58,70,73,75`(`"src.agent.self_rewrite.*"`)
- **docs**: `docs/DESIGN.md:310` (`turn_log`/`equity_log`/`trades_log` 거명)
- **`-m` 진입점**: `equity_log.py:113 __main__` — 미문서화 진입점, 새 경로 `python -m src.agent.logs.equity`
  (클린브레이크, 등록 시 기결정; non-src 참조 0 확인)
- **동적 import/`importlib`**: 0. **클래스명 직렬화**: 해당 없음(함수 위주 모듈).

## 보존해야 할 관측 가능 동작 (외부 계약)
- 9개 모듈의 모든 공개 함수/상수 시그니처·동작 byte-for-byte (특히 `AGENT_CONSTITUTION` 내용 불변).
- JSONL/CSV 산출물 경로·스키마 불변 (equity/trades/turn 로그 파일 위치는 코드 내 경로 상수 — 모듈
  위치와 무관, Stage 4에서 불변 확인).
- 변경되는 것: import 경로 + `-m` 진입 경로(클린브레이크)만.

## 특성화 테스트 (안전망)
- 기존 테스트가 9모듈 전부 커버: `test_agent(_reports)` `test_efficacy` `test_recall` `test_self_rewrite`
  `test_orchestrator_selflearning` `test_constitution_pin` `test_turn_log_f22` `test_executor` 등.
- **베이스라인: 158 passed** (이 worktree). Stage 4 내내 green 유지.

## 동시 트랙
- 다른 active 코드 트랙 없음(R9–R12 머지 완료; F71은 docs-only inception; F33 paused). R13(tests)은
  R8 머지 후 착수 — 충돌면 없음.

## 결론
이동 9 + stutter 개명 1(동일 파일) + 참조 ~50(문자열 7 포함) + docs 1 + `-m` 클린브레이크 1.
전부 T1 + 기승인 클린브레이크. 코어 루프 5파일은 불변 — T3 게이트 없음 예상.
