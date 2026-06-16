# F86 — Component Methods (signatures; 상세 규칙은 Functional Design)

## C1 — DashboardReadRoute (`dashboard-read.ts`)
```ts
// 메인 핸들러. /autostock/dashboard 이외엔 null 반환(체인 통과).
export async function route(request: Request): Promise<Response | null>

// 내부: steering 파일 best-effort 읽기 (각 파일 try/catch, 부재/파싱실패 → undefined)
function readSteeringJson(dir: string, file: string): unknown | undefined
```
- 입력: HTTP `Request`. 출력: `Response`(200 JSON) 또는 null.
- 동작: `resolveSteeringDir` → 4개 파일 read → `assembleDashboardPayload` → `Response.json(payload)`.
- 에러: 전역 try/catch → 빈/부분 payload(`published_at` 없음 → 클라 stale). 절대 5xx 미발생(NFR-3/SECURITY-15).
- 인증: 기존 basic-auth + tailscale 경계 뒤(라우트 자체는 read-only, 서명 불요 — D2).

## C2 — SteeringDirResolver
```ts
export function resolveSteeringDir(
  env: Record<string, string | undefined> = process.env,
  cwd: string = process.cwd(),
): string | null
```
- 우선순위: `env.STEERING_DIR` → `join(env.AUTOSTOCK_ROOT, "steering")` → `join(cwd, "../../steering")`.
- 존재 검증 실패/전부 미해석 → null(호출부는 빈 payload로 fail-safe).

## C3 — assembleDashboardPayload (PURE, PBT 핵심)
```ts
type RawSteering = {
  snapshot?: unknown   // snapshot.json
  health?: unknown     // health.json
  monitor?: unknown    // monitor.json
  pending?: unknown    // pending_approvals.json
  snapshotMtimeIso?: string | null
}
export function assembleDashboardPayload(s: RawSteering): DashboardPayload
```
- `DashboardPayload`(잠정; Functional Design 확정):
  ```ts
  type DashboardPayload = {
    account: { equity: number|null; cash: number|null; day_pnl_pct: number|null;
               buying_power: number|null; open_pnl: number|null; position_count: number }
    positions: Array<{ symbol: string; market_value: number|null; unrealized_pnl: number|null;
                       side: "long"|"short"; current_price: number|null }>
    health: { status?: string; ok?: boolean } | null
    pending_approvals: number
    market: { open: boolean|null; phase?: string; label?: string } | null
    agent: { current: string|null; recent: Array<{ ts?: string; action: string; symbol?: string; summary?: string }> }
    published_at: string | null
  }
  ```
- 규칙: **never-throw**. 누락/타입오염 → 해당 필드 null/empty. day_pnl_pct·buying_power = null(미발행, §0.1). positions dict→array(심볼 보존).
- `published_at`: monitor `ts` 또는 snapshot mtime; 둘 다 없으면 null(→stale).

## C4 — DashboardPoller (클라 배선; mobile-shell)
```ts
const POLL_MS = 5_000          // 튜닝 노브
const STALE_THRESHOLD_MS = 30_000  // 튜닝 노브 (isStale)
async function fetchDashboard(http): Promise<DashboardPayload | null>  // 인증 fetch, 실패→null
// createResource + setInterval; document.hidden/locked() 시 폴 스킵; onRefresh 즉시 refetch
```
- 흐름: `fetchDashboard` → `assembleSnapshot`(payload를 SnapshotSources로) → `toDashboard` → `DashboardView model`.
  `isStale(model, Date.now(), STALE_THRESHOLD_MS)` → `stale` prop. 실패/오프라인 → `EMPTY_DASHBOARD`(offline).
- 라이프사이클: `onMount` 시작, `onCleanup` 해제. background/locked 시 트래픽 중단(NFR-4).
