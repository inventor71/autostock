import type { MonitorTurn, MarketRule, InterventionMarker } from "../types"
import { DEFAULT_MARKET_RULE } from "../types"

// F25: market-aware 12h timeline. Everything is computed in absolute epoch ms
// (the session crosses local midnight in KST, so minutes-of-day is unusable).
// ET wall times are converted to instants using the IANA tz (DST-correct via Intl),
// then rendered in the operator's LOCAL timezone for labels.

/** Offset (ms) of an IANA timezone at a given UTC instant: localWall - utc. */
export function tzOffsetMs(utcMs: number, tz: string): number {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  })
  const parts = dtf.formatToParts(new Date(utcMs))
  const m: Record<string, string> = {}
  for (const p of parts) m[p.type] = p.value
  let hour = Number(m.hour)
  if (hour === 24) hour = 0 // some engines emit "24" at midnight
  const asUTC = Date.UTC(
    Number(m.year), Number(m.month) - 1, Number(m.day),
    hour, Number(m.minute), Number(m.second),
  )
  return asUTC - utcMs
}

/** Epoch ms for a wall-clock "HH:MM" on an ET calendar date, in the market tz. */
export function etWallToEpoch(etDate: string, hhmm: string, tz: string): number {
  const [y, mo, d] = etDate.split("-").map(Number)
  const [h, mi] = hhmm.split(":").map(Number)
  const guess = Date.UTC(y!, mo! - 1, d!, h!, mi!)
  // Two-pass correction: the first offset is sampled at the *guess* instant,
  // which on a DST-transition day can sit in the wrong offset zone (e.g. 04:00
  // ET pre-market on spring-forward/fall-back lands an hour off with one pass).
  // Re-sampling at the corrected instant converges for all non-folded wall times.
  const off1 = tzOffsetMs(guess, tz)
  const epoch1 = guess - off1
  const off2 = tzOffsetMs(epoch1, tz)
  return off2 === off1 ? epoch1 : guess - off2
}

export interface SessionBounds {
  preOpen: number
  regularOpen: number
  regularClose: number
  afterClose: number
  /** 12h window centered on the regular session. */
  winStart: number
  winEnd: number
}

const TWELVE_H = 12 * 60 * 60 * 1000

/** Compute the session boundary instants + the 12h window for an ET date. */
export function sessionBounds(etDate: string, rule: MarketRule): SessionBounds {
  const tz = rule.tz
  const preOpen = etWallToEpoch(etDate, rule.pre_open, tz)
  const regularOpen = etWallToEpoch(etDate, rule.regular_open, tz)
  const regularClose = etWallToEpoch(etDate, rule.regular_close, tz)
  const afterClose = etWallToEpoch(etDate, rule.after_close, tz)
  const mid = (regularOpen + regularClose) / 2
  return {
    preOpen, regularOpen, regularClose, afterClose,
    winStart: mid - TWELVE_H / 2,
    winEnd: mid + TWELVE_H / 2,
  }
}

export type MarketPhase = "pre" | "regular" | "after" | "closed"

/** Which market phase an instant falls in, per the session bounds. */
export function phaseAt(b: SessionBounds, ms: number): MarketPhase {
  if (ms >= b.regularOpen && ms < b.regularClose) return "regular"
  if (ms >= b.preOpen && ms < b.regularOpen) return "pre"
  if (ms >= b.regularClose && ms < b.afterClose) return "after"
  return "closed"
}

export interface MarkerPosition {
  turn: MonitorTurn
  x: number
  offscreen: -1 | 0 | 1   // -1 = clamped to left edge, 1 = right edge, 0 = in window
}

export interface InterventionPosition {
  intervention: InterventionMarker
  x: number
  offscreen: -1 | 0 | 1
}

export interface TickPosition {
  label: string
  x: number
}

export interface RegionSpan {
  kind: "pre" | "regular" | "after"
  x0: number
  x1: number
}

export interface LabelCell {
  kind: RegionSpan["kind"]
  x: number      // absolute timeline column of this label glyph
  ch: string     // single label character (P/R/E, O/P/E/N, A/F/T)
}

/**
 * F34: the per-column cells occupied by each region's inline label (PRE/OPEN/AFT).
 * Pure geometry — mirrors the historical `bandText` placement EXACTLY (label starts
 * one column in from the region's left edge, shown only when the region is at least
 * `label.length + 2` wide) so the labels render at the same columns they always did,
 * but now as a TOPMOST overlay layer (markers/cursor can no longer occlude them).
 * `shortOf` is injected (the component passes `phaseShort`) to keep this dependency-free
 * and unit-testable.
 */
export function labelCells(
  regions: RegionSpan[],
  barWidth: number,
  shortOf: (kind: string) => string,
): LabelCell[] {
  const cells: LabelCell[] = []
  for (const r of regions) {
    if (r.x1 <= r.x0) continue                 // region not drawn (see <Show when={r.x1>r.x0}>)
    const w = Math.max(r.x1 - r.x0, 1)
    const lbl = shortOf(r.kind)
    if (w < lbl.length + 2) continue           // no room for the inline label (matches bandText)
    for (let i = 0; i < lbl.length; i++) {
      const x = r.x0 + 1 + i
      if (x >= 0 && x < barWidth) cells.push({ kind: r.kind, x, ch: lbl[i]! })
    }
  }
  return cells
}

export interface TimelineLayout {
  bounds: SessionBounds
  markers: MarkerPosition[]
  interventions: InterventionPosition[]
  ticks: TickPosition[]
  regions: RegionSpan[]
  nowX: number            // -1 when now is outside the window
}

/** Local "HH:MM" for an epoch (operator's system timezone). */
function localHhmm(ms: number): string {
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

function tsToEpoch(ts: string | undefined | null): number | null {
  if (!ts) return null
  const ms = Date.parse(ts)
  return Number.isNaN(ms) ? null : ms
}

export function computeLayout(opts: {
  turns: MonitorTurn[]
  interventions: InterventionMarker[]
  barWidth: number
  etDate: string
  rule?: MarketRule
  now?: number
}): TimelineLayout {
  const rule = opts.rule ?? DEFAULT_MARKET_RULE
  const now = opts.now ?? Date.now()
  const bounds = sessionBounds(opts.etDate, rule)
  const span = bounds.winEnd - bounds.winStart || 1
  const usable = Math.max(opts.barWidth - 2, 1) // 1-col padding each side

  const xOf = (ms: number): number =>
    Math.round(1 + ((ms - bounds.winStart) / span) * usable)

  const clampX = (ms: number): number => Math.min(Math.max(xOf(ms), 0), opts.barWidth - 1)

  // Markers outside the 12h window are clamped to the nearest edge (with an
  // offscreen flag) instead of being dropped, so extended-hours activity — esp.
  // human interventions — stays discoverable (the window is regular-centered).
  const placed = (ms: number): { x: number; offscreen: -1 | 0 | 1 } => {
    if (ms < bounds.winStart) return { x: 0, offscreen: -1 }
    if (ms > bounds.winEnd) return { x: opts.barWidth - 1, offscreen: 1 }
    return { x: xOf(ms), offscreen: 0 }
  }

  const markers: MarkerPosition[] = []
  for (const t of opts.turns) {
    const ms = tsToEpoch(t.ts)
    if (ms == null) continue
    const p = placed(ms)
    markers.push({ turn: t, x: p.x, offscreen: p.offscreen })
  }

  const interventions: InterventionPosition[] = []
  for (const iv of opts.interventions) {
    const ms = tsToEpoch(iv.ts)
    if (ms == null) continue
    const p = placed(ms)
    interventions.push({ intervention: iv, x: p.x, offscreen: p.offscreen })
  }

  // Hourly ticks across the window, labeled in local time.
  const ticks: TickPosition[] = []
  const HOUR = 60 * 60 * 1000
  const first = Math.ceil(bounds.winStart / HOUR) * HOUR
  for (let ms = first; ms <= bounds.winEnd; ms += HOUR) {
    ticks.push({ label: localHhmm(ms), x: xOf(ms) })
  }

  // Three market regions clamped to the window.
  const regions: RegionSpan[] = [
    { kind: "pre", x0: clampX(bounds.winStart), x1: clampX(bounds.regularOpen) },
    { kind: "regular", x0: clampX(bounds.regularOpen), x1: clampX(bounds.regularClose) },
    { kind: "after", x0: clampX(bounds.regularClose), x1: clampX(bounds.winEnd) },
  ]

  const nowX = now >= bounds.winStart && now <= bounds.winEnd ? xOf(now) : -1

  return { bounds, markers, interventions, ticks, regions, nowX }
}
