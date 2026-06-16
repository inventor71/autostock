# F86 — Component Dependencies

## 의존 매트릭스

| Component | depends on | 통신 | 변경 |
|---|---|---|---|
| C1 DashboardReadRoute | C2, C3, node `fs`/`path` | in-proc fn call + 파일 read | **신규** |
| C2 SteeringDirResolver | `process.env`, cwd | — | **신규** (C1 내부) |
| C3 assembleDashboardPayload | (순수, 의존 없음) | — | **신규** (C1 내부/코어) |
| C1 mount | `server/server.ts` | 라우트 체인 1줄 | **Minor** (공유 파일) |
| C4 DashboardPoller | F79 코어, `useServer().http`, `serverFetcher` | HTTP fetch + in-proc | **Minor** (mobile-shell 배선) |
| F79 코어 (assembleSnapshot/toDashboard/isStale/DashboardView) | — | — | **무변경** (재사용) |
| python `SteeringRuntime` (snapshot/health/monitor/pending 발행) | — | 파일 write (별 프로세스) | **무변경** (read-only 의존) |

## 데이터 플로우

```
┌────────────── 폰 (PWA over tailscale TLS) ──────────────┐
│  C4 DashboardPoller  ── GET /autostock/dashboard (~5s) ──┐ │
│     │  payload                                          │ │
│     ▼                                                   │ │
│  assembleSnapshot → toDashboard → DashboardView         │ │
│                  └ isStale → stale 배지                  │ │
└─────────────────────────────────────────────────────────┘ │
                                                             │ (basic-auth + tailscale)
┌──────────────── 호스트 (autostock serve, node) ───────────▼─┐
│  server.ts ──▶ C1 DashboardReadRoute                        │
│                 ├─ C2 resolveSteeringDir(env,cwd)            │
│                 ├─ fs.read × {snapshot,health,monitor,pending}│
│                 └─ C3 assembleDashboardPayload → Response    │
└───────────────────────────▲─────────────────────────────────┘
                            │ fs read (read-only)
┌───────────────────────────┴─────────────────────────────────┐
│  <STEERING_DIR>/  (python daemon SteeringRuntime — UNCHANGED) │
│   snapshot.json · health.json · monitor.json ·               │
│   pending_approvals.json                                      │
└──────────────────────────────────────────────────────────────┘
```

## 결합/리스크
- **신규 결합 1개**: `DashboardPayload` 계약(C3↔C4). 단일 JSON 접점이라 회귀 표면 작음.
- **공유 파일(머지 주의)**: `server/server.ts`(마운트), `mobile-shell.tsx`(배선). → state.md Merge Risk Notes에 기록.
- **동시 트랙**: F84(모바일 차트)가 같은 데이터·같은 셸 의존. 본 트랙이 데이터 채널을 먼저 확립 → F84가 위에 스택.
- **언어 경계**: node가 python 발행 파일을 read만 — 계약은 "발행 JSON 스키마". 데몬 변경 없음이라 배포 순서 제약 없음(데몬이 먼저 떠 있으면 됨; 없으면 빈 payload=stale).
- **순환 의존 없음**.
