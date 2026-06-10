# Stage 2 — Tier ledger: intraday data 서브패키지화

**Track**: R10 · **Date**: 2026-06-11

| # | 변경 | Tier | 근거 |
|---|------|------|------|
| 1 | 4 모듈 `git mv` → `src/data/intraday/` + `__init__.py` 신설 | T1 | 경로만 이동, 시그니처/동작 불변 |
| 2 | 내부 cross-import 3건 + 테스트 import 4건 갱신 | T1 | 기계적 경로 치환 |
| 3 | `runtime.py:563` 문자열 경로 갱신 | T1 | 표시용 codebase tree 라벨 |
| 4 | `-m` CLI 경로 변경 (`src.data.intraday_collector` → `src.data.intraday.collector`) | **의도된 외부 변경** (T1 아님·승인 완료) | 클린 브레이크 결정 2026-06-08 (state.md) — shim 없음, post-merge-guide 필수 |
| 5 | 역할 경계 docstring (`data/intraday` vs `agent/intraday`) | T1 | 문서만 |

**T3 게이트: 없음** — 유일한 비-T1(#4)은 트랙 등록 시 이미 사용자 결정 완료.
