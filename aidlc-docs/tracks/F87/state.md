# Track F87 — 13F 브리프 bias 완화: 숏/풋 push 제거 → pull-only

> Lean follow-up to [[f81-disclosed-holdings]]. Single writer = this worktree session.

## Track Info
- **Track ID**: F87
- **Title**: 13F disclosed-holdings 브리프 bias 완화 — 숏/풋 방향을 매 턴 push 프롬프트에서 제거하고 on-demand pull 툴로만 노출
- **Type**: feature (behavior change, F81 follow-up)
- **Status**: merge-awaiting  <!-- Build & Test green 2026-06-14 -->
- **Branch**: feat/F87
- **Worktree**: .claude/worktrees/F87
- **Base commit**: f7b751d
- **Start Date**: 2026-06-14

## Why
F81 머지 후 사용자 우려: SA LP 13F는 대부분 풋(하락 베팅)이라, "SHORT NVDA…"가 **매 리서치 턴
프롬프트에 ~90일간 반복 주입**되면 에이전트가 bias·앵커링됨. 특히 shorting OFF(기본)면 숏은 칠
수도 없어 **행동가치 0 + bias만** 주입. UAQ 결정: **롱은 push 유지, 숏/풋은 push에서 제거하고
on-demand pull 툴(`disclosed_holdings`)로만 조회**.

## Scope (변경)
- `src/signals/brief.py` `to_prompt_text`: disclosed_holdings 섹션을 **LONG-only**로 렌더 +
  one-manager/contrarian 프레이밍 + "숏은 여기 없음, `disclosed_holdings` 툴로 조회" 안내.
- `src/signals/holdings/brief.py`: push용 long-only 렌더(`render_push_line`) 추가
  (`render_line` full은 유지 — pull/디버그용).
- `src/agent/tools/market.py`: 신규 `disclosed_holdings(collector)` pull 함수(숏 포함 전체 반환).
- `src/agent/tools/__main__.py`: `disclosed_holdings` 서브커맨드 + dispatch.
- `src/agent/prompts.py`: 툴 목록에 `disclosed_holdings` 엔트리 추가.
- 테스트: push=롱만(숏 미노출), pull=숏 포함.

## Merge Risk Notes
- **공유 파일**: `src/signals/brief.py`, `src/signals/holdings/brief.py`, `src/agent/tools/market.py`,
  `src/agent/tools/__main__.py`, `src/agent/prompts.py` — F81 직후라 겹침 적음(F81은 이미 main).
- **API 변경**: additive (`render_push_line` 신규, market.disclosed_holdings 신규, 서브커맨드 신규).

## Stage Progress
- [x] Workspace Detection — brownfield, F81 follow-up
- [x] Requirements/Design — UAQ 결정(숏 pull-only), lean (full inception 스킵)
- [x] Code Generation — render_push_line(long-only) + push 섹션 중립 프레이밍 + market.disclosed_holdings pull + 서브커맨드 + prompts 툴 엔트리
- [x] Build & Test — 45 passed (F87 5 + F81 40), brief/push/tools 회귀 18 passed
