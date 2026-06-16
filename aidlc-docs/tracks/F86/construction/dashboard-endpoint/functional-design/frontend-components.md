# F86 — Frontend Components (unit: dashboard-endpoint)

> 신규 뷰 컴포넌트는 **없다**. F79 `DashboardView`를 **무변경**으로 재사용하고, `mobile-shell.tsx`에
> 데이터 소스(폴링)만 배선한다. 작은 순수 헬퍼는 `dashboard-source.ts`(신규)로 분리해 단위/PBT 테스트.

## 변경 컴포넌트

### `mobile-shell.tsx` (C4 배선) — 수정
- **제거**: `const EMPTY_MODEL = toDashboard(null,{offline:false})` 고정 렌더 + "실시간 데이터 연결은 후속" 고지 문구.
- **추가 상태**: `model`(signal), `rows`(PositionRow[]), `extra`({cash,buyingPower,market,agent}), `stale`(bool).
- **추가 이펙트**: `onMount` 폴 시작(BR-11), `onCleanup` 해제. `poll()`는 `http()` 가용 시에만.
- **렌더**: `<DashboardView model={model()} positions={rows()} cash={…} buyingPower={…} market={…} agent={…} stale={stale()} onRefresh={() => { touch(); poll() }} />`
- **무영향**: 승인 시트(ConfirmSheet)·잠금 커튼·헤더 배지는 그대로(별 경로).

### `dashboard-source.ts` (신규, 순수 헬퍼 + fetch)
```ts
export const POLL_MS = 5_000
export const STALE_THRESHOLD_MS = 30_000
export type DashboardPayload = { /* domain-entities.md */ }
export function toSnapshotSources(p: DashboardPayload): SnapshotSources   // F79 정합 (순수)
export function toPositionRows(positions: DashboardPayload["positions"]): PositionRow[]  // 순수, weightPct 계산
export async function fetchDashboard(http, baseFetch=fetch): Promise<DashboardPayload | null>  // 인증 fetch, 실패→null
```
- `toSnapshotSources`/`toPositionRows`는 **순수** → 단위 + PBT(P2/P6) 대상.
- `fetchDashboard`는 `serverFetcher`(basic-auth) 기반; 비-200/throw → null(BR-13).

## 상호작용 흐름
1. 진입(`/autostock`) → 즉시 1회 폴 → 대시보드 실데이터.
2. 5s마다 갱신(포그라운드·미잠금 시). 백그라운드/잠금 → 폴 정지.
3. 상단 새로고침 탭 → 즉시 갱신.
4. 30s 이상 미갱신/오프라인 → DashboardView `stale`/offline 표시(거짓 신선 금지).

## API 통합 지점
- 단일 백엔드 엔드포인트: `GET /autostock/dashboard`(C1). 응답 = `DashboardPayload`.
- 인증: 기존 basic-auth + tailscale(읽기, 서명 불요).
