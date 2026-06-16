# F86 — Components

| ID | Component | Type | File | Responsibility |
|---|---|---|---|---|
| C1 | `DashboardReadRoute` | Server route (I/O 경계) | `opencode/src/server/autostock/dashboard-read.ts` (신규) | `GET /autostock/dashboard` 라우팅·파일 read·응답. `webauthn.ts`처럼 fork-isolated. `route(request)` export, server.ts 마운트. |
| C2 | `SteeringDirResolver` | Pure fn | C1 모듈 내 | env(`STEERING_DIR`)→`AUTOSTOCK_ROOT/steering`→cwd `../../steering` 순으로 steering 디렉터리 경로 결정. 미해석 시 null. |
| C3 | `assembleDashboardPayload` | Pure fn (PBT 핵심) | C1 모듈 내 (또는 `dashboard-read-core.ts`) | 읽은 steering JSON 객체들 → 대시보드 응답 객체. never-throw, 부분-정직(누락→null/empty). |
| C4 | `DashboardPoller` 배선 | Client (I/O 경계) | `app/src/addons/autostock/mobile-shell.tsx` (+선택 `dashboard-source.ts`) | `/autostock/dashboard` 폴링·라이프사이클(background/locked 중단)·`onRefresh`. 결과를 F79 코어로 전달. |
| (reuse) | `assembleSnapshot`, `buildDashboard` | Pure (F79 C2) | `addons/autostock/snapshot.ts` | 응답 소스 → DashboardModel. **무변경**. |
| (reuse) | `toDashboard`, `EMPTY_DASHBOARD` | Pure (F79 U3) | `addons/autostock/dashboard.ts` | never-throw 변환. **무변경**. |
| (reuse) | `isStale` | Pure (F79 C2) | `addons/autostock/snapshot.ts` | 신선도 판정. **무변경**. |
| (reuse) | `DashboardView` | View (F79 C6) | `addons/autostock/dashboard-view.tsx` | 렌더. props(model/positions/cash/market/agent/stale/onRefresh) **무변경**. |

## 인터페이스 (high-level)
- **C1** 노출: `route(request: Request): Promise<Response | null>` — `/autostock/dashboard`가 아니면 null(다음 핸들러로). server.ts 체인에 webauthn 마운트와 나란히 추가.
- **C2** 노출: `resolveSteeringDir(env, cwd): string | null`.
- **C3** 노출: `assembleDashboardPayload(sources: RawSteering): DashboardPayload` — 순수, 예외 미전파.
- **C4**: SolidJS 시그널/이펙트 — `createResource`/`setInterval` 기반 폴, `createMemo`로 model 파생.

## 비고
- 동작-critical = C2/C3(서버 순수) + F79 재사용 코어. C1/C4는 얇은 배선.
- `DashboardPayload` 형태는 F79 `assembleSnapshot`의 입력(`SnapshotSources` 인접)과 정합 — Functional Design에서 정확 스키마 고정.
