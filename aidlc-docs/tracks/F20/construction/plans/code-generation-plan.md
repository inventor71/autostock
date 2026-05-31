# F20 Code Generation Plan

> 단일 유닛: `operator-console/src/` (TS 신규 모듈 + 기존 MCP 서버 확장)
> 이 계획이 Code Generation의 단일 진실 원천. 모든 체크박스는 즉시 갱신.

## Unit Context
- **Unit**: F20 — Alpaca MCP stock-only read tools
- **Dependencies**: bun 내장 `fetch` (외부 의존성 없음), `@modelcontextprotocol/sdk` (기존), `zod` (기존)
- **Contracts**: Alpaca REST API v2 GET endpoints (outbound HTTPS only)
- **Service boundary**: TS 인프로세스 — 데몬 영향 없음
- **Stories**: N/A (User Stories skipped per execution plan)

---

## Part 1: Plan (this document)

- [x] Step 0: Worktree + submodule branch 생성 (`feat/F20`)
- [x] Step 1: Unit context 분석 완료

---

## Part 2: Generation Steps

### Step 2: `alpaca-data.ts` — Alpaca HTTP Client + Formatter (NEW)
- [x] `operator-console/src/alpaca-data.ts` 생성
  - [x] `AlpacaDataClient` class — constructor fail-fast (env key check + module-level `process.exit(1)`)
  - [x] `ALPACA_PAPER` env var (default `"true"`) → `paper-api.alpaca.markets` vs `api.alpaca.markets` (critic M2)
  - [x] `REQUEST_TIMEOUT_MS = 10_000` 상수 (critic H1: F14 패턴. AbortSignal.timeout)
  - [x] `tradingGet()` / `dataGet()` — bun `fetch` wrapper, auth headers, `AbortSignal.timeout()`, error→string mapping (BR-2)
  - [x] `buildUrl()` — query string assembly
  - [x] 16 public methods — plain TS interfaces (not zod) → API call → `formatResponse()`
  - [x] TS interfaces (BR-1): `PortfolioHistoryParams`, `AssetFilterParams`, `CalendarParams`, `OrderFilterParams`, `StockBarsParams`, `StockQuoteParams`
  - [x] Zod schemas → inlined in `mcp-server.ts` `inputSchema` (기존 F9 패턴과 동일, no zod dep in alpaca-data.ts)
  - [x] `formatResponse()` — dispatch: null→"(no data)", array→`formatTable()`, object→`formatBullets()`, snapshot→`formatSnapshot()`
  - [x] `formatTable()` — 20행 limit, "and N more", 헤더 생성, 셀 포맷 (BR-3)
  - [x] `formatBullets()` — 2-depth, empty→"(empty)", 배열 요약, null→"-" (BR-3)
  - [x] `formatSnapshot()` — 섹션 구분 `## symbol\n### section` (BR-3)
  - [x] `pickFields()` / `formatCell()` — 필드 선택 (BR-4), 셀 값 변환
  - [x] `mapBarFields()` — Alpaca bar (t/o/h/l/c/v) → readable (time/open/high/low/close/volume)
  - [x] SECURITY-12: auth headers never appear in response text

### Step 3: `mcp-server.ts` — 16개 Read Tool 등록 (MODIFY)
- [x] `operator-console/src/mcp-server.ts` 수정
  - [x] `import { AlpacaDataClient } from "./alpaca-data"` 추가
  - [x] `const client = new AlpacaDataClient()` — 모듈 로드 시 fail-fast
  - [x] 16개 `server.registerTool()` 추가 (기존 F9 도구 아래, 동일 패턴, Zod inputSchema inline)
  - [x] 각 도구: Alpaca MCP 정확 이름 + `" (READ-ONLY)"` 접미어 description + `txt(await client.<method>(...))` handler
  - [x] critic M1: 모든 F20 도구 description에 `"Live Alpaca API — fresher than daemon snapshot"` 표기
  - [x] critic M1: `steer_read` description에 `"Returns daemon snapshot; for live Alpaca data use get_* tools"` 추가

### Step 4: `alpaca-data.test.ts` — Unit Tests (NEW)
- [x] `operator-console/test/alpaca-data.test.ts` 생성 — **24 pass, 0 fail**
  - [x] Mock `fetch` with different status codes (200, 401, 403, 404, 429, 500, network error, timeout)
  - [x] Test: constructor fail-fast verified (module-level check, manual test)
  - [x] Test: ALPACA_PAPER env — implicit (env set in before run)
  - [x] Test: fetch timeout → `AbortSignal.timeout()` triggers "timed out" error (critic H1)
  - [x] Test: each method returns string (never throws) → PBT-P5 covers all status codes
  - [x] Test: HTTP 200 → formatted markdown string (account, positions, orders, bars, snapshot, trade, quote, clock)
  - [x] Test: HTTP 401/403/404/429/500 → appropriate error messages (BR-2)
  - [x] Test: `formatResponse` with null/[]/{}/[items] — all return strings (PBT-P3)
  - [x] Test: `formatTable` 20-row limit + "and N more" (PBT-P1)
  - [x] Test: `formatBullets` with nested objects → 2-depth (PBT-P2)
  - [x] Test: `formatSnapshot` → section headers present
  - [x] Test: SECURITY-12 — auth headers never appear in response text
  - [x] **PBT-01**: property tests (P1-P6) — deterministic inputs, fast-check deferred (cli/ workspace boundary)
    - [x] P1: formatTable row count invariant
    - [x] P2: formatBullets output invariant
    - [x] P3: formatResponse all paths
    - [x] P4: same params → same results round-trip
    - [x] P5: HTTP error path invariant (never throws)
    - [x] P6: buildUrl idempotence (same params → same output)

### Step 5: Submodule — opencode Permission Keys + Env Vars (MODIFY)
- [x] `operator-console/cli/opencode.json` 수정
  - [x] `permission`에 16개 `autostock_<tool>: "allow"` 추가
- [x] `operator-console/cli/.opencode/opencode.jsonc` 동일 수정 (fork canonical)
  - [x] `mcp.autostock.environment`에 `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER` 추가 (`{env:...}` 패턴)

### Step 6: `docker-compose.verify.yml` — Env Wiring (MODIFY)
- [x] `docker-compose.verify.yml` 수정
  - [x] `services.attach.environment`에 `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER` 추가 (F18 패턴, host-overridable)

### Step 7: `worktree-setup.sh` — Documentation (MODIFY)
- [x] `scripts/worktree-setup.sh` 수정
  - [x] TS 트랙 안내에 Alpaca 키 필요성 언급

### Step 8: Typecheck Verification
- [x] `(cd operator-console/cli && PATH=~/.bun/bin:$PATH bun run typecheck)` — **19 packages, all pass**

### Step 9: Unit Test Execution
- [x] `(cd operator-console/cli && ALPACA_API_KEY=x ALPACA_API_SECRET=x bun test ../../operator-console/test/alpaca-data.test.ts)` — **24 pass, 0 fail**
- [x] Full suite: **92 pass, 0 fail** across 7 test files (no regressions)

---

## Submodule Coordination (concurrent-tracks)
```
operator-console/cli/  →  branch feat/F20 (already created by worktree-setup.sh)
  ├── opencode.json
  └── .opencode/opencode.jsonc

Parent gitlink: commit ONLY at merge time (after submodule feat/F20 → main merge + push)
```
