import type { MonitorTurn, MarketRule, InterventionMarker } from "../types"
import { DEFAULT_MARKET_RULE } from "../types"
import { shiftDate } from "../hooks/use-session-data"

// F25: market-aware 12h timeline. Everything is computed in absolute epoch ms
// (the session crosses local midnight in KST, so minutes-of-day is unusable).
// ET wall times are converted to instants using the IANA tz (DST-correct via Intl),
// then rendered in the operator's LOCAL timezone for labels.
//
// F45: 24h is tiled into two 12h windows anchored at the session-bounds
// winStart. The "market window" = [winStart, winStart+12h) (regular-session-
// centered; historical F25 behavior). Its complement 12h = the "off-market
// window". `liveWindowStart` picks the tile that contains `now`, and nav
// moves ±12h at a time. `computeLayout` accepts an optional `window` so the
// component can override the x-projection range while keeping session-derived
// region boundaries unchanged.

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
  // F55: overnight ("데이마켓") session = [after_close(D), pre_open(D+1)]. It crosses ET
  // midnight, so it's derived across two calendar dates (no MarketRule schema change).
  // The previous evening's overnight is [overnightPrevOpen, preOpen); the current evening's
  // is [afterClose, overnightClose). One of the two is what's on screen in an off-market
  // window; the other clamps to 0 width. (See F55 functional design / critic HIGH.)
  /** This ET date's 04:00 pre-open == close of the *previous* evening's overnight session. */
  overnightPrevOpen: number
  /** Next ET date's 04:00 pre-open == close of *this* evening's overnight session. */
  overnightClose: number
  /** 12h window centered on the regular session. */
  winStart: number
  winEnd: number
}

/** F45: 12h window size — the unit of timeline navigation. */
export const WINDOW_MS = 12 * 60 * 60 * 1000

/** Compute the session boundary instants + the 12h window for an ET date. */
export function sessionBounds(etDate: string, rule: MarketRule): SessionBounds {
  const tz = rule.tz
  const preOpen = etWallToEpoch(etDate, rule.pre_open, tz)
  const regularOpen = etWallToEpoch(etDate, rule.regular_open, tz)
  const regularClose = etWallToEpoch(etDate, rule.regular_close, tz)
  const afterClose = etWallToEpoch(etDate, rule.after_close, tz)
  // F55: overnight boundaries on the neighbouring ET dates (DST-correct via etWallToEpoch).
  const overnightPrevOpen = etWallToEpoch(shiftDate(etDate, -1), rule.after_close, tz)
  const overnightClose = etWallToEpoch(shiftDate(etDate, +1), rule.pre_open, tz)
  const mid = (regularOpen + regularClose) / 2
  return {
    preOpen, regularOpen, regularClose, afterClose,
    overnightPrevOpen, overnightClose,
    winStart: mid - WINDOW_MS / 2,
    winEnd: mid + WINDOW_MS / 2,
  }
}

/**
 * F45: calendar date (YYYY-MM-DD) in an IANA timezone for a given epoch.
 * Use "en-CA" locale which produces ISO-ish YYYY-MM-DD — the same format
 * used throughout the timeline (etDate, session_et_date).
 */
export function etDateOf(ms: number, tz: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date(ms))
}

/**
 * F45: the start of the 12h window tile that contains `now`, anchored on the
 * session-bounds `winStart` grid. Guarantees `start <= now < start + WINDOW_MS`.
 * When `now` falls exactly on a tile boundary it chooses the later tile
 * (the `<=` is on the right side of the inequality).
 */
export function liveWindowStart(now: number, etDate: string, rule: MarketRule): number {
  const bounds = sessionBounds(etDate, rule)
  const k = Math.floor((now - bounds.winStart) / WINDOW_MS)
  return bounds.winStart + k * WINDOW_MS
}

export type MarketPhase = "pre" | "regular" | "after" | "day" | "closed"

/** Which market phase an instant falls in, per the session bounds. */
export function phaseAt(b: SessionBounds, ms: number): MarketPhase {
  if (ms >= b.regularOpen && ms < b.regularClose) return "regular"
  if (ms >= b.preOpen && ms < b.regularOpen) return "pre"
  if (ms >= b.regularClose && ms < b.afterClose) return "after"
  // F55: overnight ("데이마켓") — check both the previous and current evening spans,
  // since `b` is anchored on a single ET date but the band straddles midnight.
  if (ms >= b.overnightPrevOpen && ms < b.preOpen) return "day"
  if (ms >= b.afterClose && ms < b.overnightClose) return "day"
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
  kind: "pre" | "regular" | "after" | "day"
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
  /** F45: the instant range the layout was computed for (handy for label rendering). */
  viewRange: { start: number; end: number }
  nowX: number            // -1 when now is outside the view window
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
  /**
   * F45: optional view window override. When omitted the layout uses
   * `[bounds.winStart, bounds.winEnd]` — the historical F25 market-centered
   * 12h window — so existing callers and tests stay green.
   */
  window?: { start: number; end: number }
}): TimelineLayout {
  const rule = opts.rule ?? DEFAULT_MARKET_RULE
  const now = opts.now ?? Date.now()
  const bounds = sessionBounds(opts.etDate, rule)

  // F45: the view window drives x-projection, ticks, and nowX.
  // Regions are still derived from the session-boundary instants (they clamp
  // to the view edges, so an off-market window may show 0-width regions).
  const viewStart = opts.window?.start ?? bounds.winStart
  const viewEnd = opts.window?.end ?? bounds.winEnd
  const span = viewEnd - viewStart || 1
  const usable = Math.max(opts.barWidth - 2, 1) // 1-col padding each side

  const xOf = (ms: number): number =>
    Math.round(1 + ((ms - viewStart) / span) * usable)

  const clampX = (ms: number): number => Math.min(Math.max(xOf(ms), 0), opts.barWidth - 1)

  // Markers are placed relative to the *view* window. Those outside the view
  // clamp to the nearest edge with an offscreen flag so extended-hours activity
  // stays discoverable.
  const placed = (ms: number): { x: number; offscreen: -1 | 0 | 1 } => {
    if (ms < viewStart) return { x: 0, offscreen: -1 }
    if (ms > viewEnd) return { x: opts.barWidth - 1, offscreen: 1 }
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

  // Hourly ticks across the view window, labeled in local time.
  const ticks: TickPosition[] = []
  const HOUR = 60 * 60 * 1000
  const first = Math.ceil(viewStart / HOUR) * HOUR
  for (let ms = first; ms <= viewEnd; ms += HOUR) {
    ticks.push({ label: localHhmm(ms), x: xOf(ms) })
  }

  // F55: The 12h view window can straddle an ET midnight, so a single etDate's
  // sessionBounds may miss bands visible in the window (e.g. the after-market tail
  // from the previous ET date appears in the off-market window but the primaryEtDate
  // computed from the view midpoint is already the next day). Collect session
  // boundaries from every ET date the window overlaps (at most 2 for a 12h window)
  // and union all regions, deduplicating identical spans from neighbouring dates.
  const regionDates = new Set<string>()
  regionDates.add(etDateOf(viewStart, rule.tz))
  regionDates.add(etDateOf(viewEnd - 1, rule.tz))
  const allRegions: RegionSpan[] = []
  const seen = new Set<string>()
  for (const etd of regionDates) {
    const b = sessionBounds(etd, rule)
    const candidates: RegionSpan[] = [
      { kind: "pre",      x0: clampX(b.preOpen),      x1: clampX(b.regularOpen) },
      { kind: "regular",  x0: clampX(b.regularOpen),  x1: clampX(b.regularClose) },
      { kind: "after",    x0: clampX(b.regularClose),  x1: clampX(b.afterClose) },
      { kind: "day",      x0: clampX(b.overnightPrevOpen), x1: clampX(b.preOpen) },
      { kind: "day",      x0: clampX(b.afterClose),    x1: clampX(b.overnightClose) },
    ]
    for (const r of candidates) {
      // Deduplicate by unique (kind, epoch) — neighbouring etDates produce
      // identical day bands (etDate D's second span == etDate D+1's first span,
      // both [afterClose(D), preOpen(D+1)]), and multi-date pre/regular/after
      // bands that fall on the same epoch range can also collide.
      const key = `${r.kind}:${r.x0}:${r.x1}`
      if (!seen.has(key)) { seen.add(key); allRegions.push(r) }
    }
  }
  // Keep 0-width regions in the array (renderer handles them via r.x1 <= r.x0
  // skip) so callers that depend on the region-count / ordering stay green.
  const regions = allRegions

  const nowX = now >= viewStart && now <= viewEnd ? xOf(now) : -1

  return { bounds, markers, interventions, ticks, regions, viewRange: { start: viewStart, end: viewEnd }, nowX }
}
