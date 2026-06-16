# F86 — Domain Entities (unit: dashboard-endpoint)

기술-무관 도메인 모델. 영속 저장소 없음 — 엔티티는 **데몬 발행물(읽기)** 과 **응답 계약(쓰기)** 의 형태다.

## 1. 입력 엔티티 — Steering 발행물 (read-only, python 데몬 소유)

### SnapshotFile (`snapshot.json`)
| 필드 | 타입 | 사용 |
|---|---|---|
| `account.equity` | number | → equity |
| `account.cash` | number | → cash |
| `account.open_pnl` | number | → 보조(미실현 손익 합) |
| `account.position_count` | number | → 보조 |
| `positions` | `{ [symbol]: Position }` | dict → array |
| `market_open` | bool | market phase 폴백 |

**Position** (snapshot `positions[symbol]`): `{ qty, avg_entry_price, side: "long"|"short", current_price, market_value, unrealized_pnl }`
- (미발행: `account.day_pnl_pct`, `account.buying_power` → 응답에서 null)

### HealthFile (`health.json`)
`{ status?: string, ok?: boolean, ... }` — 없으면 health=null(unknown).

### MonitorFile (`monitor.json`)
| 필드 | 타입 | 사용 |
|---|---|---|
| `ts` | ISO str | published_at 후보 |
| `market` | object (F25 market rule) | market phase/label 소스 |
| `current_turn` | object\|null | agent.current |
| `decisions` | `Array<DecisionTail>` | agent.recent |

**DecisionTail**(monitor `decisions[]`, 구조화): `{ ts?, action?, symbol?, summary?/detail?, turn_id? }` (best-effort 키).

### PendingFile (`pending_approvals.json`)
승인 대기 항목(배열/개수) → `pending_approvals` 카운트. (라이브 ConfirmSheet 큐는 별도 이벤트 경로 — 무관.)

## 2. 출력 엔티티 — DashboardPayload (응답 계약, C3 생산)

```ts
type DashboardPayload = {
  account: {
    equity: number | null
    cash: number | null
    day_pnl_pct: number | null     // v1 미발행 → null
    buying_power: number | null    // v1 미발행 → null
    open_pnl: number | null
    position_count: number         // 기본 0
  }
  positions: Array<{
    symbol: string
    market_value: number | null
    unrealized_pnl: number | null
    return_pct: number | null      // 진입가 대비 P&L% (side 반영), DashboardView dayPct로 매핑
    side: "long" | "short"
    current_price: number | null
  }>
  health: { status?: string; ok?: boolean } | null
  pending_approvals: number        // 기본 0
  market: { open: boolean | null; phase?: string; label?: string } | null
  agent: {
    current: string | null
    recent: Array<{ ts?: string; action: string; symbol?: string; summary?: string }>
  }
  published_at: string | null      // 없으면 클라 stale
}
```

## 3. 클라 매핑 엔티티 (C4 → F79 코어/뷰)
- `DashboardPayload` → `SnapshotSources`(F79) → `assembleSnapshot` → `toDashboard` → **DashboardModel**(equity/dayPnlPct/positionCount/symbols/healthOk/pendingApprovals/asOf/offline). **무변경 재사용.**
- `DashboardPayload.positions` → **PositionRow[]**(F79 DashboardView): `{ symbol, marketValue, dayPct: return_pct, weightPct }` (weightPct = market_value / Σmarket_value).
- `cash`/`buyingPower`/`market`/`agent` → DashboardView props 직접 매핑.

## 4. 불변식 (도메인)
- 응답은 항상 위 스키마(부분이라도) — 절대 예외/부분 누락으로 깨진 객체 아님.
- `published_at` 없음 ⇒ 신선하지 않음(stale)으로 취급(거짓 신선 금지).
- `positions` 배열 길이 = snapshot positions dict 키 수(보존).
