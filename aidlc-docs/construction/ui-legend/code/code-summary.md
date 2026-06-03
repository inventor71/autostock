# Code Summary — ui-legend (F28)

> Track: F28 · Worktree: `.claude/worktrees/F28` (parent `feat/F28` + 서브모듈 `feat/F28`)
> Code Generation Part 2 결과. 구현 선례 = F29 `/codebase` verb.

## Created
- **`operator-console/src/ui-legend.json`** (parent repo) — 정적 UI 사전, **21 엔트리**:
  - Topbar 4 (date_label, date_nav, market_phase, today_cost)
  - Timeline 4 (tick_labels, now_cursor, region_bands, session_boundary)
  - Markers 7 (research ● / intraday ○ / wake ◆ / eod ▲ / reconcile ↻ / error ✕ / human ✚) — **turn-type 기준**(format.ts 검증)
  - Sidebar 4 (account, positions, round_trip, recent_fills)
  - Status 2 (run_state, market)
  - `_note` 헤더 = drift 동기화 안내.
- **`operator-console/cli/packages/tui-trading/AGENTS.md`** (서브모듈) — TUI 변경 시 ui-legend.json 동기화 규약.

## Modified (parent repo `operator-console/src/`)
- **`parser.ts`** — `READ_VERBS`에 `"ui-legend"` 추가 (codebase 옆). schema.ts 미변경(READ_VERBS pseudo-verb는 SteeringVerb 아님).
- **`steer-handler.ts`** — `node:fs` readFileSync import + `loadUiLegend()`(try/catch→[]) + `handleUiLegend(raw)` export + `handleSteerRead`에 `if(draft.verb==="ui-legend")` 분기. legend는 `new URL("./ui-legend.json", import.meta.url)`로 런타임 read(top-level import 미사용 — malformed 시 graceful). element는 `draft.args.raw`에서 split.
- **`mcp-server.ts`** — `steer_read` description에 `LEGEND verb: /ui-legend [element]` 줄 추가 (에이전트 discovery — MANDATORY).

## Tests (parent `operator-console/test/`)
- `parser.test.ts` +1: `/ui-legend` readOnly verb, element는 `args.raw`에 보존(파서 미split).
- `steer-handler.test.ts` +3: 전체 legend / 단일 element(meaning 포함) / unknown→not-found 에러.
- **결과: `bun test ./test/` = 131 pass, 0 fail (8 files).**

## 검증
- ui-legend.json valid JSON, 21 엔트리.
- `import.meta.url` legend 로드 동작 확인(테스트가 실제 파일 읽어 통과).
- parent는 빌드/typecheck 단계 없이 `bun run`으로 직접 실행 → `bun test`가 TS 파싱·실행 검증.
- 서브모듈 cli 코드 미변경(doc 1개) → tsgo 영향 없음.

## Invariants 유지
- 파이썬 데몬 변경 0 · schema.ts/golden contract 미관여 · 0 new runtime deps.
- normal-mode 권한: `autostock_steer_read` 기존 allow 그대로(새 verb 자동 허용, F26 미변경).
- 읽기 전용(readOnly verb) — 주문/쓰기 경로 무관.

## Drift 관리
- PR 규약(사용자 결정): UI 변경 시 ui-legend.json 동기화. tui-trading/AGENTS.md + ui-legend.json `_note`로 명시.

## 알려진 사항
- 전체 repo `bun test`는 서브모듈 opencode fork 자체 테스트의 pre-existing timeout 1건 포함(bash-tool 취소 테스트, effect 기반, F28 무관).
- 마커 의미는 코드(format.ts)와 일치하도록 작성 — 당초 질문의 ◆BUY/○SELL 가정은 실제와 달라 정정함(실제는 turn-type 기준).
