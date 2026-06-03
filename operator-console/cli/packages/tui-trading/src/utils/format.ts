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
  if (verb === "buy" || verb === "place_order") return "green"
  if (verb.startsWith("cancel")) return "gray"
  return "red"
}

// F25: market-phase labels/colors for the timeline (region bands + now badge).
const PHASE_LABEL: Record<string, string> = {
  pre: "PRE-MARKET", regular: "REGULAR", after: "AFTER-HRS", closed: "CLOSED",
}
const PHASE_SHORT: Record<string, string> = {
  pre: "PRE", regular: "OPEN", after: "AFT", closed: "—",
}
const PHASE_COLOR: Record<string, string> = {
  pre: "#7faaff", regular: "#5fd38d", after: "#c98bdb", closed: "gray",
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

export function fmtCost(usd: number): string {
  return `$${usd.toFixed(2)}`
}

export function fmtDuration(ms: number | null): string {
  if (ms == null) return "—"
  if (ms < 1000) return `${ms}ms`
  return `${Math.round(ms / 1000)}s`
}

export function fmtPnl(pnl: number): { text: string; color: string } {
  const sign = pnl >= 0 ? "+" : ""
  return {
    text: `${sign}$${pnl.toFixed(2)}`,
    color: pnl >= 0 ? "green" : "red",
  }
}
