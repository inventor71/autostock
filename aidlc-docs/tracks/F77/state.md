# Track F77 — StockTwits 리테일 sentiment 신호

> Per-track state. **Single writer = this track's worktree session.**

## Track Info
- **Track ID**: F77
- **Title**: StockTwits 자가 라벨(Bull/Bear) 집계 — 시간당 유니버스 스윕 + 베이스라인 + research/intraday 브리프 (F61 소스)
- **Type**: feature
- **Status**: merge-awaiting  <!-- Build & Test ALL GREEN 2026-06-13 -->
- **Branch**: feat/F77
- **Worktree**: .claude/worktrees/F77
- **Submodule branch**: — (monorepo; operator-console 무접촉 예정)
- **Base commit**: bacd341
- **Start Date**: 2026-06-13

## Extension Configuration
- **Security Baseline**: Enabled — 적용: SECURITY-03/05/07/10/15 (개인정보 미저장·응답 검증·단일 HTTPS 출처·무신규의존성·fail-safe), 나머지 N/A
- **Property-Based Testing**: Enabled (Partial) — 집계/z-score 순수 함수 + 레코드 round-trip

## Scope
범위 B (사용자 확정): 데몬 시간당 전 유니버스 스윕(무인증 StockTwits 심볼 스트림,
자가 라벨만 집계) + `workspace/sentiment/` 히스토리 + 베이스라인 z-score 이상치 →
research/intraday 브리프 섹션. **wake 트리거/고빈도 폴링/본문 분석/TUI verb는 범위 외**
(베이스라인 축적 후 후속 트랙). 관련: [[f61-market-signals]], F72 screening(ET 날짜 키 선례).

## Merge Risk Notes
> merge-awaiting 전환 시 작성.

- **공유 파일 (주의)**: `src/signals/{settings,collector,brief}.py`, `src/trading/modes/agent.py`(스케줄러 잡), `config/settings.yaml`
- **API/시그니처 변경**: `assemble_brief()`에 keyword `sentiment_outliers` 추가(기존 호출 호환), `MarketSignalBrief.sentiment_outliers` 필드+`is_empty()` 포함, `BriefAssembler.__init__`에 `sentiment_lines_fn` 키워드 추가(기본 None), `SignalsConfig.sentiment` 서브모델 추가
- **알려진 동시 변경**: F74(prompt eval — prompts 인접 가능), F76(filedrop — 무관 예상)

## Stage Progress
- [x] Workspace Detection — brownfield, codekb 존재 → RE skip
- [x] Requirements Analysis — standard (승인 2026-06-13)
- [x] User Stories — SKIP (단일 운영자, 수용기준 requirements §6)
- [x] Workflow Planning — 승인 2026-06-13
- [x] Application Design — SKIP (F61 플러그인 경계 내)
- [x] Units Generation — SKIP (단일 유닛)
- [x] Construction — unit "stocktwits-sentiment"
  - [x] Functional Design — 승인 2026-06-13
  - [x] Code Generation Part 1 (계획)
  - [x] Code Generation Part 2 — 구현+테스트, 커밋 13365c1
- [x] Build & Test — ALL GREEN (py 1210, 신규 25 + 브리프 렌더, 라이브 스모크 실데이터) + post-merge guide
