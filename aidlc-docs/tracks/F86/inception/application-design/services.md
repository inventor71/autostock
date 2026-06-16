# F86 — Services / Orchestration

신규 서비스 클래스는 없다(추가형 read 라우트 + 클라 배선). 두 개의 얇은 오케스트레이션 흐름만 존재.

## S1 — Server dashboard-read flow (C1)
```
Request(GET /autostock/dashboard)
  → [기존] basic-auth + tailscale 경계 통과 (인증)
  → resolveSteeringDir(env, cwd)            (C2)
  → readSteeringJson × {snapshot, health, monitor, pending_approvals}  (각 try/catch, best-effort)
  → assembleDashboardPayload(raw)           (C3, never-throw)
  → Response.json(payload, 200)
```
- **Fail-safe**: 디렉터리 미해석/파일 부재/JSON 깨짐 → 부분/빈 payload(200). 전역 try/catch가 예외를
  흡수해 절대 5xx로 셸을 깨지 않음(NFR-3 / SECURITY-15).
- **Read-only**: 어떤 상태도 변경하지 않음. mutating 게이트(F75/F79 S1)와 무관.
- **마운트**: `server.ts`에서 webauthn 라우트와 같은 자리에 `m.route(request) ?? ...` 체인으로 1줄 추가.
- **로깅**: 접근/에러는 기존 serve 로깅 사용. 잔고/토큰 등 민감값 로그 미기록(SECURITY-03).

## S2 — Client polling flow (C4)
```
onMount → fetchDashboard() 1회 + setInterval(POLL_MS)
  매 tick: document.hidden || locked() ? skip
                                       : fetchDashboard()
             → assembleSnapshot → toDashboard → setModel
             → isStale → setStale
onRefresh(tap) → 즉시 fetchDashboard()
onCleanup → clearInterval
```
- **효율(NFR-4)**: background/locked 시 폴 중단 → 불필요 트래픽 없음. POLL_MS(5s) = 데몬 publish 주기 정합.
- **회복(NFR-3)**: fetch 실패/네트워크 단절 → `EMPTY_DASHBOARD`(offline=true) → DashboardView 오프라인 표시.
- **재사용**: 변환·신선도·렌더는 F79 코어(`assembleSnapshot`/`toDashboard`/`isStale`/`DashboardView`) — 무변경.

## 오케스트레이션 경계
- 서버↔클라 단일 접점 = `DashboardPayload` JSON 계약. python 데몬 발행 스키마는 read-only 입력(무변경).
- 라이브 승인 시트(ConfirmSheet)는 **별도 경로**(permission 이벤트 구독) — 이 트랙과 독립, 무변경.
