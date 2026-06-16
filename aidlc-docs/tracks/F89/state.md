# Track F89 — 13F를 참조 데이터화 (pull 전용): 유니버스 편입 OFF + push 브리프 제거

> Lean follow-up to [[f81-disclosed-holdings]] / F87. Single writer = this worktree session.

## Track Info
- **Track ID**: F89
- **Title**: 13F disclosed-holdings를 참조 데이터(pull 전용)로 전환 — 유니버스 자동 편입 OFF + 매 턴 push 브리프 제거, on-demand `disclosed_holdings` 툴로만 노출
- **Type**: feature (behavior change, F81/F87 follow-up)
- **Status**: merge-awaiting  <!-- Build & Test green 2026-06-16 -->
- **Branch**: feat/F89
- **Worktree**: .claude/worktrees/F89
- **Base commit**: f17a36f
- **Start Date**: 2026-06-16

## Why
사용자 판단: 단일 기관(SA LP) 보유종목을 봇 거래 유니버스에 자동 편입하는 건 자의적·단일소스
bias. 대신 **참조 데이터화** — 봇 매매에 영향 0, 에이전트가 필요할 때만 조회. (다기관 컨센서스로
키우는 건 별도 후속 옵션으로 보류.)

## Scope (변경)
- `config/settings.yaml`: SA LP provider `overlay: false` (유니버스 자동 편입 OFF).
- `src/signals/brief.py` `to_prompt_text`: disclosed_holdings **push 섹션 제거** (pull 전용).
- `src/signals/holdings/brief.py`: `render_push_line`(F87) 제거 — push가 없어졌으므로 unused.
  `render_line`(full)은 유지.
- pull 경로 유지: collector가 brief.disclosed_holdings 채움 + `disclosed_holdings` 툴 그대로.
- 테스트: push에 13F 섹션 없음 + pull 툴은 여전히 전체(숏 포함) 반환.

## Merge Risk Notes
- **공유 파일**: `src/signals/brief.py`, `src/signals/holdings/brief.py`, `config/settings.yaml`,
  `tests/signals/test_holdings_brief_push.py` (F87이 방금 건드림 — F87은 이미 main).
- **API 변경**: `render_push_line` 제거(내부 함수, 외부 호출부 없음). 나머지 additive/삭제.

## Stage Progress
- [x] Workspace Detection — brownfield, F81/F87 follow-up
- [x] Requirements/Design — UAQ 결정(참조 데이터화/pull 전용), lean
- [x] Code Generation — config overlay:false + to_prompt_text push 섹션 제거 + render_push_line 제거 + 테스트 갱신
- [x] Build & Test — 54 passed (holdings+brief 회귀 포함), overlay 통합 sanity(universe injection []), pull 툴 유지
