// F79 C2 — SnapshotController (pure core): assemble the dashboard snapshot from the
// separate read sources (account / positions / health / pending) the PWA already has,
// and decide staleness (NFR-7). No server-side unified endpoint is introduced — the
// client assembles, and the existing never-throw `toDashboard` consumes it (D-AD-2).

import { toDashboard, type DashboardModel } from "./dashboard"

export type SnapshotSources = {
  account?: { equity?: number | null; day_pnl_pct?: number | null } | null
  positions?: Array<{ symbol?: string | null }> | null
  health?: { status?: string; ok?: boolean } | null
  pendingApprovals?: number
  publishedAt?: string | null
}

/**
 * Shape the read sources into the snapshot object `toDashboard` expects. Best-effort:
 * missing pieces become empty/zero so `toDashboard` renders a partial-but-honest model.
 */
export function assembleSnapshot(s: SnapshotSources): Record<string, unknown> {
  return {
    account: s.account ?? {},
    positions: Array.isArray(s.positions) ? s.positions : [],
    health: s.health ?? null,
    pending_approvals: typeof s.pendingApprovals === "number" ? s.pendingApprovals : 0,
    published_at: typeof s.publishedAt === "string" ? s.publishedAt : null,
  }
}

/** One call: read sources -> DashboardModel. */
export function buildDashboard(s: SnapshotSources, opts: { offline?: boolean } = {}): DashboardModel {
  return toDashboard(assembleSnapshot(s), opts)
}

/**
 * Stale when offline, when there is no `asOf`, when `asOf` is unparseable, or when the
 * snapshot is older than `thresholdMs`. Fail-safe: never reports a missing/old snapshot
 * as fresh (NFR-7 / SECURITY-15).
 */
export function isStale(model: DashboardModel, nowMs: number, thresholdMs: number): boolean {
  if (model.offline) return true
  if (!model.asOf) return true
  const t = Date.parse(model.asOf)
  if (Number.isNaN(t)) return true
  return nowMs - t > thresholdMs
}
