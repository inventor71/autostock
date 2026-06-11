# Tier Ledger — R8 `src/agent/` 재구조화

범위: agent 최상위 9모듈 → logs/·learning/ 서브패키지 + reports stutter (구조점검 #1)
작성일: 2026-06-11

## T1 — 동작 보존 (자율 진행)
| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| 1 | `git mv` ×3 → `logs/{equity,trades,turn}.py` (+빈 `logs/__init__.py`) | 로그 기록/조회 함수·JSONL/CSV 산출 경로 동일 | `test_agent.py`(equity), `test_turn_log_f22.py`, intraday fills 테스트 | 파일 위치만 이동; 데이터 경로는 코드 내 상수로 모듈 위치와 무관 |
| 2 | `git mv` ×5 → `learning/{efficacy,recall,self_rewrite,constitution,review}.py` (+빈 `__init__.py`) | 자가학습 API·`AGENT_CONSTITUTION` byte 불변 | `test_efficacy/recall/self_rewrite/constitution_pin/orchestrator_selflearning` | 동상 |
| 3 | `git mv agent_reports.py reports.py` | 리포트 생성 함수 동일 | `test_agent_reports.py` | stutter 해소, 시그니처 불변 |
| 4 | 일반 import ~40곳 경로 갱신 | import 동일 객체 | 위 테스트 전부 + 전체 스위트 | 기계적 치환(`rg -l` 파일 단위) |
| 5 | **문자열 monkeypatch 7곳** 갱신 (`"src.agent.agent_reports.os.replace"`→`"src.agent.reports.os.replace"`, `"src.agent.self_rewrite.*"`→`"src.agent.learning.self_rewrite.*"`) | setattr 타깃 해석 동일 | 해당 테스트 자체가 검증 | 전수검사로 특정됨 |
| 6 | **모듈-객체 import 2곳**: `orchestrator.py:334,546` `from src.agent import agent_reports` → `from src.agent import reports as agent_reports`가 아니라 **native하게 `from src.agent import reports` + 사용부 `reports.X`로 갱신** | 호출 결과 동일 | `test_agent_reports` + orchestrator 경로 테스트 | alias 잔존 금지([[feedback-monorepo-refactor-as-native]]) |
| 7 | `docs/DESIGN.md:310` 모듈명 갱신 | (문서) | n/a | 정합성 |

## T2 — 안전한 확장
없음.

## T3 — 의도 변경 (기승인 클린브레이크)
| # | 변경 내용 | 이유 | 영향 범위 | 사용자 결정 |
|---|-----------|------|-----------|-------------|
| 1 | `python -m src.agent.equity_log` → `python -m src.agent.logs.equity` (`__main__`:113, shim 없음) | 미문서화 진입점; 별칭 유지 = clutter | non-src 참조 0(전수 확인) — 수동 호출 습관만 영향 → post-merge-guide 1줄 | **승인** — 2026-06-08 클린브레이크 정책 |

## 정지 지점
- [x] T3 = 기승인 클린브레이크 1건뿐 — 게이트 불필요
- [x] 모든 T1 항목이 기존 agent 테스트(158)로 보호됨
