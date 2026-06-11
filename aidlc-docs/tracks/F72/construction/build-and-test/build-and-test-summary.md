# F72 — Build & Test Summary

**Date**: 2026-06-11 · **Worktree**: `.claude/worktrees/F72` (feat/F72, base 76ff7b6) · **결과: ALL GREEN**

## 실행 결과

| 검증 | 명령 | 결과 |
|---|---|---|
| Python 신규 단위+PBT | `venv/bin/python -m pytest tests/test_screening_log.py -q` | 11 passed (hypothesis round-trip 포함) |
| Python 전체 회귀 | `venv/bin/python -m pytest tests/ -q --ignore=tests/benchmark` | **1054 passed** |
| 콘솔 변경 표면 | `bun test test/parser.test.ts test/steer-handler.test.ts test/filedrop.test.ts test/contract.test.ts test/f21-validation.test.ts` | 86 pass / 0 fail |
| 콘솔 나머지 파일 | `bun test test/alpaca-data.test.ts test/launcher*.test.ts` | 82 pass / 0 fail |
| 라이브 스모크 (C3) | 임시 워크스페이스에 실제 yfinance scoreboard 실행 → scan.json 생성 → `handleSteerRead("/screening")` 렌더 → 날짜 인자 검증/no-data 확인 | 전부 정상 |

주의: 콘솔 테스트는 **파일 명시**로 실행할 것 — `bun test`(무인자) 또는 `bun test test/`는
경로 필터가 `cli/`(opencode 서브모듈)의 자체 스위트까지 매칭해 수 분간 돌며 무관한 실패를 낸다.
환경: `ALPACA_API_KEY`/`ALPACA_API_SECRET` 더미 값 필요 (alpaca-data 모듈 import 가드).

## Extension 컴플라이언스 (최종)

- **SECURITY-03**: 준수 — Loguru 경고 로깅; 스크리닝 레코드는 공개 시장 데이터 + 에이전트 판단 텍스트만 (토큰/PII 없음).
- **SECURITY-05**: 준수 — `/screening` 날짜 인자 `^\d{4}-\d{2}-\d{2}$` allowlist를 경로 사용 전 검증 (주입 테스트 포함).
- **SECURITY-15**: 준수 — record_scan 모든 예외 → warning+None; 콘솔 read 전부 fail-closed, 내부 오류 미노출.
- 나머지 SECURITY 룰: N/A (신규 endpoint/인증/암호화 자산/인프라 없음).
- **PBT (Partial)**: 준수 — scan rows 직렬화 round-trip property test (hypothesis). 날짜 검증은 주입 케이스 예제 기반(콘솔에 PBT 프레임워크 부재 — fast-check 미사용 관례 유지).

## 회귀 외 수리 (pre-existing 복구)

`operator-console/test/contract.test.ts`가 main에서 **이미 2건 실패** 중이었음:
F53이 read-only verb(thesis/theses)를 file-drop SteeringVerb union/ALL_VERBS에 넣었고(golden엔 없음),
F52가 Python/golden에 추가한 `exec_outcome` event kind가 TS 미러에 누락. 본 트랙에서
read verb를 union에서 제거(codebase/ui-legend 선례와 일치)하고 exec_outcome을 미러에 추가해 복구.
