# F86 — Code Generation Plan (unit: dashboard-endpoint)

Worktree: `.claude/worktrees/F86` · branch `feat/F86`. ✅ 전 항목 완료.

## Server (opencode package)
- [x] Add `fast-check` devDependency to `packages/opencode/package.json` (match app `4.6.0`) + `bun install`
- [x] `src/server/autostock/dashboard-read.ts` (신규, fork-isolated):
  - [x] `resolveSteeringDir(env, cwd)` (C2, 순수) — STEERING_DIR → AUTOSTOCK_ROOT/steering → cwd/../../steering
  - [x] `assembleDashboardPayload(raw)` (C3, 순수, never-throw) — BR-3..BR-8, return_pct BR-5, day_pnl/buying_power=null
  - [x] `route(request)` (C1) — path guard, `checkBasicAuth`(reuse webauthn), read 4 files best-effort, 200 JSON, fail-safe
  - [x] `EMPTY_PAYLOAD` const
- [x] `src/server/server.ts` — mount dashboard-read in fetch chain (1 line, after webauthn)
- [x] `test/autostock-dashboard.test.ts` — example(완전/빈/깨진/short/health-overall) + PBT(P1/P2/P3/P5, fast-check) → 13 pass

## Client (app package)
- [x] `src/addons/autostock/dashboard-source.ts` (신규):
  - [x] `POLL_MS`, `STALE_THRESHOLD_MS`, `DashboardPayload` 타입
  - [x] `toSnapshotSources(payload)` (순수) — F79 SnapshotSources 정합
  - [x] `toPositionRows(positions)` (순수) — weightPct 계산
  - [x] `toMarket(market)` (순수) — phase 매핑 + open 폴백
  - [x] `fetchDashboard(http, baseFetch?)` — 인증 fetch, 실패→null
- [x] `src/addons/autostock/mobile-shell.tsx` — 폴링 배선(onMount/onCleanup, background/locked 중단), DashboardView 실데이터 props, 고지문구 제거
- [x] `src/addons/autostock/dashboard-source.test.ts` — example + PBT(P2/P4/P6, fast-check) → 11 pass

## Verify
- [x] `bun run typecheck` (opencode + app) → clean
- [x] `bun test test/autostock-dashboard.test.ts` (opencode) → 13 pass
- [x] `bun test --preload ./happydom.ts src/addons/autostock` (app) → 52 pass (F79 41 + F86 11)
- [x] **real-data smoke** (실 steering/*.json against assembleDashboardPayload) — account/positions(return_pct)/agent/market/published_at 정상. **버그 2건 발견·수정**: ① PBT P1이 `pending`/`position_count` 음수/소수 미정규화 발견 → sanitize; ② 실 `health.json`은 `status`가 아니라 `overall`("OK"/"ERROR") 사용 + 2.7KB 블롭 → `{status,ok,summary}` 정규화·축약(payload 3KB+→1.4KB)
