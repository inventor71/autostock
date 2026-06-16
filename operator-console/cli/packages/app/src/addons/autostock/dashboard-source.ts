// F86 — client data source for the mobile dashboard. Pure mappers (tested) + a thin
// authenticated fetch to the F86 server route GET /autostock/dashboard. The shell polls
// this and feeds the result into the F79 cores (assembleSnapshot → toDashboard) and
// DashboardView. No new view: DashboardView (F79 C6) is reused unchanged.

import type { ServerConnection } from "@/context/server"
import type { SnapshotSources } from "./snapshot"
import type { PositionRow } from "./dashboard-view"
import { serverFetcher } from "./webauthn-fetch"

/** Poll cadence — matches the daemon's ~5s snapshot publish (NFR-5). Tuning knob. */
export const POLL_MS = 5_000
/** A snapshot older than this is shown as stale (NFR-7 / isStale). Tuning knob. */
export const STALE_THRESHOLD_MS = 30_000

/** Server response contract (mirrors opencode server/autostock/dashboard-read.ts). */
export type DashboardPayload = {
  account: {
    equity: number | null
    cash: number | null
    day_pnl_pct: number | null
    buying_power: number | null
    open_pnl: number | null
    position_count: number
  }
  positions: Array<{
    symbol: string
    market_value: number | null
    unrealized_pnl: number | null
    return_pct: number | null
    side: "long" | "short"
    current_price: number | null
  }>
  health: { status?: string; ok?: boolean; summary?: string } | null
  pending_approvals: number
  market: { open: boolean | null; phase?: string; label?: string } | null
  agent: { current: string | null; recent: Array<{ ts?: string; action: string; symbol?: string; summary?: string }> }
  published_at: string | null
}

/** Shape the payload into F79 `SnapshotSources` (consumed by assembleSnapshot/toDashboard). */
export function toSnapshotSources(p: DashboardPayload): SnapshotSources {
  return {
    account: { equity: p.account.equity, day_pnl_pct: p.account.day_pnl_pct },
    positions: p.positions.map((r) => ({ symbol: r.symbol })),
    health: p.health,
    pendingApprovals: p.pending_approvals,
    publishedAt: p.published_at,
  }
}

/**
 * Rich per-position rows for DashboardView. `weightPct` = position market value as a share of
 * total absolute market value (handles shorts' negative values); `dayPct` carries the
 * side-aware P&L-since-entry % the server computed. Pure.
 */
export function toPositionRows(positions: DashboardPayload["positions"]): PositionRow[] {
  const total = positions.reduce((sum, r) => sum + Math.abs(r.market_value ?? 0), 0)
  return positions.map((r) => ({
    symbol: r.symbol,
    marketValue: r.market_value,
    dayPct: r.return_pct,
    weightPct: total > 0 && r.market_value !== null ? (Math.abs(r.market_value) / total) * 100 : null,
  }))
}

/** Map the server market block to the DashboardView phase. */
export function toMarket(
  m: DashboardPayload["market"],
): { phase: "pre" | "regular" | "after" | "closed"; label?: string } | undefined {
  if (!m) return undefined
  const phase = m.phase === "pre" || m.phase === "regular" || m.phase === "after" || m.phase === "closed" ? m.phase : undefined
  if (phase) return { phase, label: m.label }
  // Fall back to the open boolean when no explicit phase is published.
  if (m.open === true) return { phase: "regular", label: m.label }
  if (m.open === false) return { phase: "closed", label: m.label }
  return undefined
}

/**
 * Authenticated GET of the dashboard snapshot. Returns null on any network/HTTP/parse failure
 * so the caller can render the offline model (BR-13) rather than holding a stale value.
 */
export async function fetchDashboard(
  http: ServerConnection.HttpBase,
  baseFetch: typeof fetch = fetch,
): Promise<DashboardPayload | null> {
  try {
    const res = await serverFetcher(http, baseFetch)("/autostock/dashboard", { method: "GET" })
    if (!res.ok) return null
    return (await res.json()) as DashboardPayload
  } catch {
    return null
  }
}
