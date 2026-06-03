# Code Generation Plan — ui-legend (F28)

> Track: F28 · Unit: `ui-legend` · Brownfield, parent-repo TS only
> Single source of truth for Code Generation. 0 new runtime deps.
> 구현 선례 = F29 `/codebase` verb (parser READ_VERBS + handler 분기 + tests).

## Unit Context
- **Goal**: normal-mode 에이전트가 `steer_read{command:"/ui-legend [element]"}`로 자기 TUI 요소(타임라인/사이드바/상태줄)의 의미를 설명.
- **변경 표면**: parent repo `operator-console/src/` (`parser.ts`, `steer-handler.ts`, `mcp-server.ts` + 정적 `ui-legend.json`) + **서브모듈 doc 1개** (`packages/tui-trading/AGENTS.md` — drift 규약, 사용자 결정 2026-06-02). **schema.ts·파이썬 데몬 미변경.** 서브모듈에 doc 1개가 들어가므로 서브모듈 브랜치 `feat/F28` 필요.
- **Dependencies**: F26(머지됨, normal allowlist), F25/F6(TUI 코드 — 의미 작성 위해 *읽기*만).
- **Design refs**: `aidlc-docs/construction/ui-legend/functional-design/{domain-entities,business-logic-model,business-rules}.md`.

## Requirements traceability
- FR-1 → Step 1 (정적 ui-legend.json)
- FR-2 → Step 2/3/4 (verb 등록 + handler 분기 + description)
- FR-3 (전체 TUI 커버) → Step 1
- FR-4 (normal 접근) → 코드 변경 없음(기존 allow), Step 5에서 검증
- BR-0 (READ_VERBS만) → Step 2
- BR-3 (element 추출 handler) → Step 3
- BR-4 (readFileSync, import 금지) → Step 3
- HIGH#1 (description MANDATORY) → Step 4

---

## Steps

### Step 0 — Worktree gate (Part 2 first action, blocking)
- [x] `scripts/worktree-setup.sh F28 --ts` — worktree `.claude/worktrees/F28` (parent `feat/F28` + 서브모듈 `feat/F28`), bun install + tsgo ready. ✅
- [x] 이후 모든 변경은 이 worktree 안에서. 진행/audit는 `tracks/F28/`.

### Step 1 — 정적 `ui-legend.json` 작성 (FR-1, FR-3) ✅
- [x] `operator-console/src/ui-legend.json` 생성, **21 엔트리** (topbar 4 + timeline 4 + 마커 7 + 사이드바 4 + 상태줄 2). `_note` 헤더 포함.
- [x] TUI 코드 읽어 의미 정확화 — **마커는 turn-type 기준**(●research ○intraday ◆wake ▲eod ↻reconcile ✕error ✚human; format.ts 검증). 질문 가정(◆BUY 등) 정정. topbar $X.XX=today_cost_usd(timeline-bar.tsx:70,128 검증).
- [ ] 전체 TUI 커버 — F25/F6/상태줄 TUI 코드를 **읽어** 정확한 의미 작성:
  - **Topbar**: `topbar.date`(날짜+Today), `topbar.date_nav`(`[<] [>]` 날짜 이동), `topbar.today_cost`(=오늘 턴 비용 합계, 화면 $ 값). 근거: `operator-console/cli/.../timeline-bar.tsx:70,128`, `use-monitor-data.ts:58`.
  - **타임라인**: `timeline.ruler`(시간축 09:30–16:00), 마커 `timeline.marker.buy`(◆), `.sell`(○), `.adjust_stop`(+), `.hold`(⧫).
  - **사이드바**: `sidebar.account.{equity,cash,invested,open_pnl,positions}`, `sidebar.positions`, `sidebar.round_trip`, `sidebar.recent_fills`.
  - **상태줄**: `status.run_state`(RUNNING/HALTED/PAUSED), `status.market`(OPEN/CLOSED/PRE-MARKET).
- [ ] meaning은 한국어 완전 문장 + "화면의 그 값" 식 안내(현재값은 안 주므로). id unique 확인(BR-1).

### Step 2 — `parser.ts`: READ_VERBS에 verb 등록 (BR-0, FR-2①) ✅
- [x] `parser.ts` READ_VERBS에 `"ui-legend"` 추가 (codebase 옆). schema.ts 미변경.

### Step 3 — `steer-handler.ts`: `handleSteerRead` 분기 (FR-2②, BR-3, BR-4) ✅
- [x] `node:fs` readFileSync import + `loadUiLegend()`(try/catch→[]) + `handleUiLegend(raw)` export + `if(draft.verb==="ui-legend")` 분기(codebase 분기 다음). element는 `draft.args.raw` split. top-level import 미사용.

### Step 4 — `mcp-server.ts`: description에 verb 광고 (HIGH#1, MANDATORY) ✅
- [x] `steer_read` description에 `LEGEND verb: /ui-legend [element] — ...` 추가(CODEBASE 줄 다음).

### Step 4b — drift 규약 명시: `packages/tui-trading/AGENTS.md` 신규 (서브모듈) ✅
- [x] `operator-console/cli/packages/tui-trading/AGENTS.md` 신규 — "TUI 요소 변경 시 ui-legend.json 동기화" 규약 명시. (서브모듈 feat/F28, 부모 gitlink는 머지 시.)

### Step 5 — 테스트 (parser + handler) ✅
- [x] `parser.test.ts`: `/ui-legend` readOnly verb, element는 raw 보존(파서 미split) — 1 test.
- [x] `steer-handler.test.ts`: 전체 legend / 단일 element / not-found 에러 — 3 tests.

### Step 6 — 빌드·타입체크·회귀 ✅
- [x] ui-legend.json valid JSON (21 엔트리).
- [x] `bun test ./test/` (parent F28 범위) = **131 pass, 0 fail** (신규 4 테스트 포함).
- [x] parent `operator-console/`는 tsconfig/typecheck 스크립트 없음(`bun run`으로 직접 실행) → `bun test`가 TS 파싱·실행·import.meta.url legend 로드까지 검증. 서브모듈 cli 코드 미변경(AGENTS.md doc 1개) → tsgo 영향 없음.
- [참고] 전체 repo `bun test`는 서브모듈 opencode fork 자체 테스트의 무관한 pre-existing timeout 1건 포함(bash-tool 취소 테스트, F28 무관).

### Step 7 — 코드 요약 문서 ✅
- [x] `aidlc-docs/construction/ui-legend/code/code-summary.md` 작성.

---

## 예상 규모
- **수정 3** (parser.ts, steer-handler.ts, mcp-server.ts) + **신규 1** (ui-legend.json) + 테스트 2 보강 + **서브모듈 doc 1** (tui-trading/AGENTS.md).
- 코드 ~30-40줄 + legend 데이터(엔트리 ~15개). 0 new deps. 서브모듈 변경 = doc 1개(코드 아님).

## 검증 전략 (Build & Test 단계)
- 단위: verb 파싱, element 필터, not-found, 파일-누락 graceful.
- 통합: 실제 `steer_read{command:"/ui-legend ..."}` 호출 형태(가능하면 worktree에서 MCP 핸들러 직접 호출).
- 회귀: `operator-console` 전체 테스트 + tsgo 클린.
- 수동(선택): normal 모드 콘솔에서 "탑바 $ 뭐야?" → 에이전트가 `/ui-legend` 호출하는지.
