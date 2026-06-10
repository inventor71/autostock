# Stage 1 — Baseline: `data/intraday_*` 전수 인벤토리

**Track**: R10 · **Date**: 2026-06-11 · **Base**: 0106a8b

## 이동 대상 (4 모듈)
`src/data/intraday_{features,store,collector,analysis}.py` → `src/data/intraday/{features,store,collector,analysis}.py`

## 라이브 참조 전수 (rg, 워크스페이스 전체)
| # | 위치 | 종류 | 처리 |
|---|------|------|------|
| 1 | `intraday_store.py:18` → features | 내부 import | 경로 갱신 |
| 2 | `intraday_collector.py:31,32` → features/store | 내부 import | 경로 갱신 |
| 3 | `intraday_analysis.py:210` → store | 지연 import | 경로 갱신 |
| 4 | `intraday_collector.py:14-17(docstring),144(argparse prog)` | **`-m` CLI 표면** | 클린 브레이크 → `python -m src.data.intraday.collector` |
| 5 | `intraday_analysis.py:212(argparse prog)` | **`-m` CLI 표면** | → `python -m src.data.intraday.analysis` |
| 6 | `src/agent/steering/runtime.py:563` | **문자열 경로** (F29 codebase tree) | `"src/data/intraday/features.py"` 로 갱신 |
| 7 | `tests/test_intraday.py:16,22,23,24` | 테스트 import | 경로 갱신 (내용 불변) |

## 오탐/제외 (확인 완료)
- `tests/test_intraday_orchestrator.py` — `src.agent.intraday`/prompts import (R10 무관).
- `"data/intraday"` 문자열(`intraday_store.py:3,24`) — **파일시스템 CSV 경로**(gitignored 데이터 디렉터리).
  모듈 경로와 무관, 충돌 없음. 그대로 유지.
- `aidlc-docs/codekb/nfr-design.md:25` — codekb는 single-writer=CI([[codekb-ci-headless]]) → 손대지 않음, CI가 자동 갱신.
- 과거 트랙 문서(F1/F30/F37 등) — 역사 기록, 갱신 대상 아님.
- monkeypatch/문자열 모듈 참조 — **0건** (rg 확인).

## 심볼 stutter 검토 (state.md 요구사항)
모듈 내 정의 전수(`class/def`): `compute_session_features`, `IntradayFeatureStore`, `Hypothesis`,
`evaluate_hypothesis`, `analyze`, `sessionize`, `collect` 등 — **모듈 접두(`intraday_`)를 반복하는
심볼 없음** → 심볼 개명 불필요, 모듈 이동만 수행. (`IntradayFeatureStore`는 도메인 기술명으로 유지.)

## 기존 테스트 net (green 기준선)
`tests/test_intraday.py` — 4개 모듈 전부 커버. 이동 전 통과 확인 후 이동.
