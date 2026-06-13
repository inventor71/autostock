# F77 — Build & Test Summary

**Date**: 2026-06-13 · **Worktree**: `.claude/worktrees/F77` (feat/F77, base bacd341) · **결과: ALL GREEN**

## 실행 결과

| 검증 | 명령 | 결과 |
|---|---|---|
| 신규 단위+PBT | `venv/bin/python -m pytest tests/signals/test_sentiment.py tests/signals/test_sentiment_sweep.py -q` | 25 passed (hypothesis 4종 포함) |
| signals 스위트 | `pytest tests/signals/ -q` | 93 passed (브리프 렌더 테스트 추가 포함) |
| 전체 회귀 | `pytest tests/ -q --ignore=tests/benchmark` | **1210 passed** |
| 라이브 스모크 | 실제 StockTwits 6심볼 스윕 → 6/6 수집 → 합성 베이스라인 + 실측 current → 이상치 선별 → 브리프 렌더 | 정상 (`TSLA bull 27% (usually 75%, z=-44.3) — bearish shift`) |

## 라이브 스모크에서의 실전 발견 2건 (반영됨)

1. **UA 차단**: StockTwits가 기본 `python-requests` User-Agent를 403으로 차단 —
   데스크톱 UA 헤더 추가로 해결 (코드 주석 + post-merge guide에 기록).
2. **시간 창 동작 확인**: 스모크 시각(21:27 ET)이 창 밖이라 스윕이 no-op —
   설계 의도대로 동작함을 실증.

## Extension 컴플라이언스 (최종)

- **SECURITY-03**: 준수 — 집계 숫자만 저장(본문/닉네임 無), Loguru 구조 로깅.
- **SECURITY-05**: 준수 — 외부 JSON 관대+타입 검증(pydantic SentimentRecord ge=0), 심볼 정규화, 예상 밖 구조 skip.
- **SECURITY-07/10**: 준수 — 신규 출처 api.stocktwits.com HTTPS 단일, 신규 의존성 0 (requests 기존 스택).
- **SECURITY-15**: 준수 — 소스 raise→스윕 격리/턴 degraded, 스케줄러로 예외 전파 0 (테스트 `test_any_exception_is_absorbed`).
- 나머지 SECURITY 룰: N/A (인증/암호화 자산/배포 인프라 변경 없음).
- **PBT (Partial)**: 준수 — bull_ratio 범위, baseline 총정의성, zscore 무예외, 레코드 round-trip.

## 주의 (실행 방법)

- 콘솔(TS) 변경 없음 — bun test 불필요.
- 시간 창 밖에서 수동 스윕 테스트 시 `window_et: ["00:00","23:59"]`로.
