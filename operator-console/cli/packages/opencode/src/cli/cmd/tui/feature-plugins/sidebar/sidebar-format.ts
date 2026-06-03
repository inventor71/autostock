// F8 — pure formatting / derivation helpers for the status.py-rich sidebar.
// Kept free of solid-js / OpenTUI imports so they are unit-testable with bun
// (mirrors F4's shared dispatch.ts: verified logic that can't drift from the UI).
// Mirrors scripts/status.py (_order_role, _pnl_markup, Δ-to-trigger, P&L%).

export interface OrderLike {
  symbol?: string
  side?: string
  order_type?: string
  stop_price?: number | null
  limit_price?: number | null
  current_price?: number | null
}

export interface PositionLike {
  qty?: number
  avg_entry_price?: number
  current_price?: number
  unrealized_pnl?: number
}

// status.py _order_role: BUY → entry; STOP/STOP_LIMIT → stop(-loss); else take(-profit).
export function orderRole(o: OrderLike): string {
  if ((o.side ?? "").toLowerCase() === "buy") return "entry"
  const t = (o.order_type ?? "").toLowerCase()
  if (t === "stop" || t === "stop_limit") return "stop"
  return "take"
}

export function orderTrigger(o: OrderLike): number | undefined {
  if (o.limit_price != null) return o.limit_price
  if (o.stop_price != null) return o.stop_price
  return undefined
}

// Δ from current price to the trigger in %, or undefined when no usable current price.
export function orderDelta(o: OrderLike): number | undefined {
  const trig = orderTrigger(o)
  const cur = o.current_price
  if (trig == null || cur == null || !Number.isFinite(cur) || cur === 0) return undefined
  return (trig / cur - 1) * 100
}

export function pnlPct(p: PositionLike): number | undefined {
  if (p.avg_entry_price == null || p.current_price == null || p.avg_entry_price === 0) return undefined
  return (p.current_price / p.avg_entry_price - 1) * 100
}

// status.py-style signed percent with a direction arrow (▲ up / ▼ down).
export function fmtPct(n?: number): string {
  if (n == null || !Number.isFinite(n)) return ""
  return `${n >= 0 ? "▲" : "▼"}${n >= 0 ? "+" : ""}${n.toFixed(1)}%`
}

export function fmtPrice(n?: number | null): string {
  if (n == null || !Number.isFinite(n)) return ""
  return n.toFixed(2)
}

// true → "up" color (green), false → "down" color (red). Caller maps to theme.
export function isUp(n?: number): boolean {
  return (n ?? 0) >= 0
}

// F13 — recent fills can span multiple days, but the rows only carried HH:MM. Local
// "MM/DD" (matches hhmm()'s local-time basis). NaN/empty ts → "" (no prefix).
export function mmdd(ts?: string): string {
  if (!ts) return ""
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ""
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`
}

// F13 — date column for a fills row: show "MM/DD " only when this row's local date
// differs from the previous (newer) row's, else blank-pad to the same width so the
// HH:MM column stays aligned ("MM/DD ".length === 6). Empty when ts is unusable.
export function fillDatePrefix(ts?: string, prevTs?: string): string {
  const cur = mmdd(ts)
  if (!cur) return ""
  return cur === mmdd(prevTs) ? "      " : `${cur} `
}
