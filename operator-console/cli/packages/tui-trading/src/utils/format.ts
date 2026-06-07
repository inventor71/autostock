import type { TurnType } from "../types"

const GLYPH: Record<string, string> = {
  research: "●",
  intraday: "○",
  wake: "◆",
  eod: "▲",
  reconcile: "↻",
}

const COLOR: Record<string, string> = {
  research: "cyan",
  intraday: "white",
  wake: "yellow",
  eod: "magenta",
  reconcile: "blue",
}

const ACTION_COLOR: Record<string, string> = {
  BUY: "green",
  SELL: "red",
  HOLD: "gray",
  ADJUST_STOP: "yellow",
}

export function markerGlyph(type: string, health: string): string {
  if (health === "error") return "✕"
  return GLYPH[type] ?? "·"
}

export function markerColor(type: string, health: string): string {
  if (health === "error") return "red"
  return COLOR[type] ?? "white"
}

export function actionColor(action: string): string {
  return ACTION_COLOR[action] ?? "white"
}

// F25: human trade interventions use a distinct glyph/color from agent turns.
export function interventionGlyph(_verb: string): string {
  return "✚"
}

export function interventionColor(verb: string): string {
  // Buy-ish green, sell/flatten/close red, cancels gray.
  // F60: short opens (sell_short), cover closes (buy_to_cover — a buy-side risk-reducing action).
  if (verb === "buy" || verb === "place_order" || verb === "cover") return "green"
  if (verb.startsWith("cancel")) return "gray"
  return "red"
}

// F69: system-health status → glyph + color for the timeline status cell and the
// health overlay. `stale`/no-data renders as a dim SKIPPED-style marker.
const HEALTH_GLYPH: Record<string, string> = {
  OK: "✓", WARNING: "⚠", ERROR: "✗", CRITICAL: "⊘", SKIPPED: "○",
}
const HEALTH_COLOR: Record<string, string> = {
  OK: "#5fd38d", WARNING: "#d4b86a", ERROR: "#e06c75", CRITICAL: "#ff5f5f", SKIPPED: "gray",
}
export function healthGlyph(status: string, stale = false): string {
  if (stale) return "○"
  return HEALTH_GLYPH[status] ?? "○"
}
export function healthColor(status: string, stale = false): string {
  if (stale) return "gray"
  return HEALTH_COLOR[status] ?? "gray"
}

// F25: market-phase labels/colors for the timeline (region bands + now badge).
const PHASE_LABEL: Record<string, string> = {
  pre: "PRE-MARKET", regular: "REGULAR", after: "AFTER-HRS", day: "DAY-MKT", closed: "CLOSED",
}
const PHASE_SHORT: Record<string, string> = {
  pre: "PRE", regular: "OPEN", after: "AFT", day: "DAY", closed: "—",
}
const PHASE_COLOR: Record<string, string> = {
  // F55: "데이마켓"(overnight) — amber, distinct from pre(blue)/regular(green)/after(purple).
  pre: "#7faaff", regular: "#5fd38d", after: "#c98bdb", day: "#d4b86a", closed: "gray",
}
export function phaseLabel(p: string): string { return PHASE_LABEL[p] ?? p }
export function phaseShort(p: string): string { return PHASE_SHORT[p] ?? p }
export function phaseColor(p: string): string { return PHASE_COLOR[p] ?? "white" }

/** F25: format a tz-aware ISO timestamp as local HH:MM. */
export function fmtLocalHhmm(iso: string): string {
  if (!iso) return ""
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return iso.slice(11, 16)
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

/** Local MM-DD for an epoch (operator's system timezone). */
function localMmdd(ms: number): string {
  const d = new Date(ms)
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/** Local HH:MM for an epoch (operator's system timezone). */
function localHhmmEpoch(ms: number): string {
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

/**
 * F45: format a view-window epoch range as a compact local datetime label.
 * e.g. "06-04 20:00 → 06-05 08:00" (date repeated when the window crosses midnight).
 */
export function fmtWindowRange(start: number, end: number): string {
  const sd = localMmdd(start)
  const ed = localMmdd(end)
  const sh = localHhmmEpoch(start)
  const eh = localHhmmEpoch(end)
  return sd === ed ? `${sd} ${sh} → ${eh}` : `${sd} ${sh} → ${ed} ${eh}`
}

export function fmtCost(usd: number): string {
  return `$${usd.toFixed(2)}`
}

// F58: sum cost_usd of the turns whose ts falls in the half-open view window
// [startMs, endMs). Lets the NavRow show the cost for ANY window (live or past),
// not just the live ET-session total. Turns with an unparseable ts are skipped.
export function windowedCost(
  turns: ReadonlyArray<{ ts: string; cost_usd: number }>,
  startMs: number,
  endMs: number,
): number {
  let sum = 0
  for (const t of turns) {
    const ms = Date.parse(t.ts)
    if (Number.isNaN(ms) || ms < startMs || ms >= endMs) continue
    sum += t.cost_usd || 0
  }
  return sum
}

export function fmtDuration(ms: number | null): string {
  if (ms == null) return "—"
  if (ms < 1000) return `${ms}ms`
  return `${Math.round(ms / 1000)}s`
}

// F44: live-elapsed clock for the in-flight turn label (minutes/hours aware, unlike
// fmtDuration which only ever prints whole seconds). e.g. 9s · 3m12s · 1h02m.
export function fmtElapsedClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`
  return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`
}

// F44: the in-flight turn progress label, e.g. "research · 3m12s · +1 queued".
// Returns null when no turn is in flight (caller renders an idle state). Pure so the
// formatting is unit-testable; the component supplies nowMs (blink-driven re-render).
export function fmtTurnLabel(
  turn: { type: string; started_at: string } | null,
  queued: number,
  nowMs: number = Date.now(),
): string | null {
  if (!turn) return null
  const elapsed = fmtElapsedClock(nowMs - Date.parse(turn.started_at))
  const q = queued > 0 ? ` · +${queued} queued` : ""
  return `${turn.type} · ${elapsed}${q}`
}

export function fmtPnl(pnl: number): { text: string; color: string } {
  const sign = pnl >= 0 ? "+" : ""
  return {
    text: `${sign}$${pnl.toFixed(2)}`,
    color: pnl >= 0 ? "green" : "red",
  }
}
