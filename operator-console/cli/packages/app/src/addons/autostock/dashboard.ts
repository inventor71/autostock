// F71 U3 — dashboard model: shape the deterministic `steer_read` snapshot into the home
// panel view-model (US-2). Pure transform — the view binds to this; no SDK/DOM here so the
// "한눈 확인" logic (what's healthy, how many pending) is unit-tested in isolation.

export type DashboardModel = {
  equity: number | null
  dayPnlPct: number | null
  positionCount: number
  symbols: string[]
  healthOk: boolean | null // null = unknown (no health published yet)
  pendingApprovals: number
  asOf: string | null // ISO timestamp of the snapshot, or null
  offline: boolean
}

export const EMPTY_DASHBOARD: DashboardModel = {
  equity: null,
  dayPnlPct: null,
  positionCount: 0,
  symbols: [],
  healthOk: null,
  pendingApprovals: 0,
  asOf: null,
  offline: true,
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

/** Build the dashboard from a steer_read status snapshot (best-effort, never throws). */
export function toDashboard(snapshot: unknown, opts: { offline?: boolean } = {}): DashboardModel {
  if (opts.offline || snapshot === null || typeof snapshot !== "object") {
    return { ...EMPTY_DASHBOARD, offline: opts.offline ?? true }
  }
  const s = snapshot as Record<string, unknown>
  const account = (s.account ?? {}) as Record<string, unknown>
  const positions = Array.isArray(s.positions) ? (s.positions as Array<Record<string, unknown>>) : []
  const health = (s.health ?? null) as Record<string, unknown> | null
  const pending = Array.isArray(s.pending_approvals)
    ? s.pending_approvals.length
    : num(s.pending_approvals) ?? 0

  return {
    equity: num(account.equity),
    dayPnlPct: num(account.day_pnl_pct ?? s.day_pnl_pct),
    positionCount: positions.length,
    symbols: positions
      .map((p) => (typeof p.symbol === "string" ? p.symbol : null))
      .filter((x): x is string => x !== null),
    healthOk: health === null ? null : health.status === "ok" || health.ok === true,
    pendingApprovals: pending,
    asOf: typeof s.published_at === "string" ? s.published_at : null,
    offline: false,
  }
}

/** A short one-line summary for the collapsed/notification view. */
export function dashboardSummary(m: DashboardModel): string {
  if (m.offline) return "오프라인 — 서버에 연결되지 않음"
  const eq = m.equity === null ? "—" : `$${m.equity.toLocaleString()}`
  const pnl = m.dayPnlPct === null ? "" : ` (${m.dayPnlPct >= 0 ? "+" : ""}${m.dayPnlPct.toFixed(2)}%)`
  const health = m.healthOk === null ? "?" : m.healthOk ? "●" : "✗"
  const pend = m.pendingApprovals > 0 ? ` · 승인대기 ${m.pendingApprovals}` : ""
  return `${eq}${pnl} · 포지션 ${m.positionCount} · 건강 ${health}${pend}`
}
