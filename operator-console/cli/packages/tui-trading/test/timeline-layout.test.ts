import { expect, test, describe } from "bun:test"
import {
  tzOffsetMs,
  etWallToEpoch,
  etDateOf,
  liveWindowStart,
  sessionBounds,
  computeLayout,
  phaseAt,
  labelCells,
  WINDOW_MS,
  type RegionSpan,
} from "../src/utils/timeline-layout"
import { phaseShort } from "../src/utils/format"
import { shiftDate } from "../src/hooks/use-session-data"
import { DEFAULT_MARKET_RULE, type MonitorTurn, type InterventionMarker } from "../src/types"

const ET = "America/New_York"

describe("tzOffsetMs", () => {
  test("EDT is UTC-4 in summer", () => {
    // 2026-06-01 12:00 UTC — ET is EDT (-4h)
    const ms = Date.UTC(2026, 5, 1, 12, 0)
    expect(tzOffsetMs(ms, ET)).toBe(-4 * 60 * 60 * 1000)
  })
  test("EST is UTC-5 in winter", () => {
    // 2026-01-15 12:00 UTC — ET is EST (-5h)
    const ms = Date.UTC(2026, 0, 15, 12, 0)
    expect(tzOffsetMs(ms, ET)).toBe(-5 * 60 * 60 * 1000)
  })
})

describe("etWallToEpoch", () => {
  test("9:30 ET on a summer date resolves to 13:30 UTC", () => {
    const ms = etWallToEpoch("2026-06-01", "09:30", ET)
    expect(new Date(ms).toISOString()).toBe("2026-06-01T13:30:00.000Z")
  })
  test("9:30 ET on a winter date resolves to 14:30 UTC", () => {
    const ms = etWallToEpoch("2026-01-15", "09:30", ET)
    expect(new Date(ms).toISOString()).toBe("2026-01-15T14:30:00.000Z")
  })

  // F25 critic HIGH#1: two-pass DST correction. On transition days the guess
  // instant lands in the wrong offset zone for pre-market; verify it round-trips.
  const readBackEt = (ms: number) =>
    new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(ms))

  test("pre-market 04:00 round-trips on spring-forward day", () => {
    expect(readBackEt(etWallToEpoch("2026-03-08", "04:00", ET))).toBe("04:00")
  })
  test("pre-market 04:00 round-trips on fall-back day", () => {
    expect(readBackEt(etWallToEpoch("2026-11-01", "04:00", ET))).toBe("04:00")
  })
  test("all session boundaries round-trip on a normal day", () => {
    for (const hhmm of ["04:00", "09:30", "16:00", "20:00"]) {
      expect(readBackEt(etWallToEpoch("2026-06-01", hhmm, ET))).toBe(hhmm)
    }
  })
})

describe("sessionBounds", () => {
  test("regular session is 6.5h; window is exactly 12h centered on it", () => {
    const b = sessionBounds("2026-06-01", DEFAULT_MARKET_RULE)
    expect(b.regularClose - b.regularOpen).toBe((6 * 60 + 30) * 60 * 1000)
    expect(b.winEnd - b.winStart).toBe(12 * 60 * 60 * 1000)
    const mid = (b.regularOpen + b.regularClose) / 2
    expect((b.winStart + b.winEnd) / 2).toBe(mid)
  })
  test("ordering pre < open < close < after", () => {
    const b = sessionBounds("2026-06-01", DEFAULT_MARKET_RULE)
    expect(b.preOpen).toBeLessThan(b.regularOpen)
    expect(b.regularOpen).toBeLessThan(b.regularClose)
    expect(b.regularClose).toBeLessThan(b.afterClose)
  })
})

describe("computeLayout", () => {
  const turn = (ts: string, id = "R1"): MonitorTurn => ({
    id, type: "research", ts, cost_usd: 1, num_decisions: 1,
    duration_ms: 1000, summary: "x", health: "ok",
  })

  test("a 10:00 ET turn lands inside the regular region", () => {
    const layout = computeLayout({
      turns: [turn("2026-06-01T10:00:00-04:00")],
      interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    const reg = layout.regions.find((r) => r.kind === "regular")!
    const x = layout.markers[0]!.x
    expect(x).toBeGreaterThanOrEqual(reg.x0)
    expect(x).toBeLessThanOrEqual(reg.x1)
  })

  test("regions present and ordered (incl. F55 overnight day spans)", () => {
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.regions.map((r) => r.kind)).toEqual(["pre", "regular", "after", "day", "day"])
  })

  test("nowX is -1 when now is outside the window", () => {
    // now far in the future
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: "2026-06-01",
      now: Date.UTC(2030, 0, 1),
    })
    expect(layout.nowX).toBe(-1)
  })

  test("intervention markers are placed", () => {
    const iv: InterventionMarker = {
      ts: "2026-06-01T10:30:00-04:00", et_date: "2026-06-01",
      verb: "buy", symbol: "AAPL", outcome: "executed", detail: "10sh",
    }
    const layout = computeLayout({
      turns: [], interventions: [iv], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.interventions.length).toBe(1)
    expect(layout.interventions[0]!.intervention.symbol).toBe("AAPL")
  })

  test("markers with bad timestamps are skipped (never throws)", () => {
    const layout = computeLayout({
      turns: [turn("not-a-date")], interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.markers.length).toBe(0)
  })

  // F25 critic HIGH#2: off-window markers clamp to the edge instead of vanishing.
  test("early pre-market marker clamps to left edge (offscreen -1)", () => {
    // 04:30 ET is before the 06:45 ET window start
    const layout = computeLayout({
      turns: [turn("2026-06-01T04:30:00-04:00")], interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.markers.length).toBe(1)
    expect(layout.markers[0]!.offscreen).toBe(-1)
    expect(layout.markers[0]!.x).toBe(0)
  })
  test("late after-hours marker clamps to right edge (offscreen 1)", () => {
    // 19:30 ET is after the 18:45 ET window end
    const layout = computeLayout({
      turns: [turn("2026-06-01T19:30:00-04:00")], interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.markers[0]!.offscreen).toBe(1)
    expect(layout.markers[0]!.x).toBe(99)
  })
  test("in-window marker has offscreen 0", () => {
    const layout = computeLayout({
      turns: [turn("2026-06-01T10:00:00-04:00")], interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.markers[0]!.offscreen).toBe(0)
  })
})

describe("phaseAt", () => {
  const b = sessionBounds("2026-06-01", DEFAULT_MARKET_RULE)
  const at = (hhmm: string) => phaseAt(b, etWallToEpoch("2026-06-01", hhmm, "America/New_York"))
  test("classifies each phase", () => {
    // F55: 00:00–04:00 and 20:00–24:00 are now the overnight ("데이마켓") session, not closed.
    expect(at("03:00")).toBe("day")     // overnight (prev evening's span, into this morning)
    expect(at("05:00")).toBe("pre")     // pre-market
    expect(at("10:00")).toBe("regular") // regular session
    expect(at("17:00")).toBe("after")   // after-hours
    expect(at("21:00")).toBe("day")     // overnight (this evening's span)
  })
  test("boundaries are half-open (open inclusive, close exclusive)", () => {
    expect(at("09:30")).toBe("regular")  // exactly open
    expect(at("16:00")).toBe("after")    // exactly close → after
    expect(at("04:00")).toBe("pre")      // F55: overnight closes at 04:00 → pre takes over
    expect(at("20:00")).toBe("day")      // F55: after closes at 20:00 → overnight takes over
  })
})

// F34: PRE/OPEN/AFT labels are rendered as a topmost overlay via `labelCells`.
// The placement must match the historical inline-band layout exactly (label one
// column in from the region's left edge), so markers/cursor no longer occlude it.
describe("labelCells", () => {
  test("places each label one column in from its region's left edge", () => {
    const regions: RegionSpan[] = [
      { kind: "pre", x0: 1, x1: 30 },
      { kind: "regular", x0: 30, x1: 70 },
      { kind: "after", x0: 70, x1: 99 },
    ]
    const cells = labelCells(regions, 100, phaseShort)
    // PRE at 2,3,4 · OPEN at 31..34 · AFT at 71,72,73
    expect(cells.filter((c) => c.kind === "pre").map((c) => [c.x, c.ch]))
      .toEqual([[2, "P"], [3, "R"], [4, "E"]])
    expect(cells.filter((c) => c.kind === "regular").map((c) => [c.x, c.ch]))
      .toEqual([[31, "O"], [32, "P"], [33, "E"], [34, "N"]])
    expect(cells.filter((c) => c.kind === "after").map((c) => [c.x, c.ch]))
      .toEqual([[71, "A"], [72, "F"], [73, "T"]])
  })

  test("skips a region with no room for its label (width < len + 2)", () => {
    // OPEN needs width >= 6; give it 5.
    const cells = labelCells([{ kind: "regular", x0: 10, x1: 15 }], 100, phaseShort)
    expect(cells).toEqual([])
  })

  test("skips a zero/negative-width region (not drawn)", () => {
    expect(labelCells([{ kind: "pre", x0: 20, x1: 20 }], 100, phaseShort)).toEqual([])
    expect(labelCells([{ kind: "pre", x0: 20, x1: 10 }], 100, phaseShort)).toEqual([])
  })

  test("clips label glyphs to the bar width", () => {
    // OPEN would occupy columns 96..99 from x0=95; barWidth 98 ⇒ keep 96,97 only.
    const cells = labelCells([{ kind: "regular", x0: 95, x1: 130 }], 98, phaseShort)
    expect(cells.map((c) => c.x)).toEqual([96, 97])
    expect(cells.map((c) => c.ch)).toEqual(["O", "P"])
  })

  test("real layout: every label cell lands inside its own region span", () => {
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 120, etDate: "2026-06-01",
    })
    const cells = labelCells(layout.regions, 120, phaseShort)
    expect(cells.length).toBeGreaterThan(0)
    for (const c of cells) {
      const r = layout.regions.find((rr) => rr.kind === c.kind)!
      expect(c.x).toBeGreaterThan(r.x0)       // strictly inside (one column in)
      expect(c.x).toBeLessThan(r.x1)
    }
  })
})

describe("shiftDate", () => {
  test("forward and back are inverse", () => {
    expect(shiftDate("2026-06-01", 1)).toBe("2026-06-02")
    expect(shiftDate("2026-06-01", -1)).toBe("2026-05-31")
    expect(shiftDate(shiftDate("2026-06-01", 1), -1)).toBe("2026-06-01")
  })
  test("crosses month boundary", () => {
    expect(shiftDate("2026-06-30", 1)).toBe("2026-07-01")
  })
})

// ──────────── F45: 12h window auto-select + nav ────────────

describe("etDateOf", () => {
  test("summer EDT: 10:00 ET = calendar date matches", () => {
    // 2026-06-01 14:00 UTC = 10:00 EDT → ET date 2026-06-01
    const ms = Date.UTC(2026, 5, 1, 14, 0, 0)
    expect(etDateOf(ms, ET)).toBe("2026-06-01")
  })
  test("winter EST: 10:00 ET = calendar date matches", () => {
    const ms = Date.UTC(2026, 0, 15, 15, 0, 0) // 10:00 EST
    expect(etDateOf(ms, ET)).toBe("2026-01-15")
  })
  test("late night ET crosses UTC midnight: 22:00 ET 06-01 = 02:00Z 06-02", () => {
    const ms = Date.UTC(2026, 5, 2, 2, 0, 0) // 22:00 EDT June 1
    expect(etDateOf(ms, ET)).toBe("2026-06-01")
  })
  test("just after ET midnight: 00:01 ET", () => {
    const ms = Date.UTC(2026, 5, 1, 4, 1, 0) // 00:01 EDT
    expect(etDateOf(ms, ET)).toBe("2026-06-01")
  })
})

describe("liveWindowStart", () => {
  const rule = DEFAULT_MARKET_RULE
  const date = "2026-06-01"

  test("now in the market window returns winStart", () => {
    const b = sessionBounds(date, rule)
    // a moment inside the market window (10:00 ET)
    const now = etWallToEpoch(date, "10:00", ET)
    const start = liveWindowStart(now, date, rule)
    expect(start).toBe(b.winStart)
    expect(now).toBeGreaterThanOrEqual(start)
    expect(now).toBeLessThan(start + WINDOW_MS)
  })

  test("now in the off-market window returns winStart + 12h", () => {
    const b = sessionBounds(date, rule)
    // 21:00 ET is after the market window (winEnd ~18:45 ET)
    const now = etWallToEpoch(date, "21:00", ET)
    const start = liveWindowStart(now, date, rule)
    expect(start).toBe(b.winStart + WINDOW_MS)
    expect(now).toBeGreaterThanOrEqual(start)
    expect(now).toBeLessThan(start + WINDOW_MS)
  })

  // PBT-1: ∀now — now is always inside the returned tile
  test("PBT: liveWindowStart always contains now (summer day sweep)", () => {
    const b = sessionBounds(date, rule)
    // Sweep every 30min across 48h from winStart
    for (let offset = 0; offset < 48 * 60 * 60 * 1000; offset += 30 * 60 * 1000) {
      const now = b.winStart + offset
      const start = liveWindowStart(now, date, rule)
      expect(now).toBeGreaterThanOrEqual(start)
      expect(now).toBeLessThan(start + WINDOW_MS)
    }
  })

  // PBT-2: adjacent tiles are exactly 12h apart and non-overlapping
  test("PBT: two consecutive tiles partition 24h without gap or overlap", () => {
    const b = sessionBounds(date, rule)
    // a now in the market window
    const t1 = liveWindowStart(b.winStart + 1000, date, rule)
    // a now in the off-market window
    const t2 = liveWindowStart(b.winStart + WINDOW_MS + 1000, date, rule)
    expect(t2).toBe(t1 + WINDOW_MS)
    expect(t1 + WINDOW_MS).toBe(t2)
  })

  test("PBT: every now in a 48h sweep falls into exactly one of two tile types", () => {
    const b = sessionBounds(date, rule)
    const tile0 = b.winStart
    const tile1 = b.winStart + WINDOW_MS
    for (let offset = 0; offset < 48 * 60 * 60 * 1000; offset += 37 * 60 * 1000) {
      const now = b.winStart + offset
      const start = liveWindowStart(now, date, rule)
      expect([tile0, tile0 + 2 * WINDOW_MS, tile1, tile1 + 2 * WINDOW_MS]).toContain(start)
    }
  })

  // PBT-3: the market window is always the session-bounds window (regular-session-centered)
  test("market-window tile matches sessionBounds.winStart", () => {
    const b = sessionBounds(date, rule)
    // A moment well inside the regular session always lands in the market window.
    const now = etWallToEpoch(date, "12:00", ET)
    expect(liveWindowStart(now, date, rule)).toBe(b.winStart)
  })
})

describe("computeLayout with window (F45)", () => {
  const rule = DEFAULT_MARKET_RULE
  const date = "2026-06-01"

  const turn = (ts: string, id = "T1"): MonitorTurn => ({
    id, type: "intraday", ts, cost_usd: 0, num_decisions: 0,
    duration_ms: null, summary: "", health: "ok",
  })

  test("without window param: backward compat (same as before F45)", () => {
    const layout = computeLayout({
      turns: [turn("2026-06-01T10:00:00-04:00")],
      interventions: [], barWidth: 100, etDate: date,
    })
    expect(layout.viewRange.start).toBe(layout.bounds.winStart)
    expect(layout.viewRange.end).toBe(layout.bounds.winEnd)
    expect(layout.nowX).toBe(-1) // default now is outside historical 2026 view
    expect(layout.regions.map((r) => r.kind)).toEqual(["pre", "regular", "after", "day", "day"])
  })

  test("nowX is in view range when now is inside the window", () => {
    const b = sessionBounds(date, rule)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: date,
      window: { start: b.winStart + WINDOW_MS, end: b.winStart + 2 * WINDOW_MS },
      now: b.winStart + WINDOW_MS + 3_600_000, // 1h into off-market window
    })
    expect(layout.nowX).toBeGreaterThanOrEqual(0)
    expect(layout.nowX).toBeLessThan(100)
  })

  test("off-market window: pre and regular clamp to 0; after partially overlaps", () => {
    const b = sessionBounds(date, rule)
    // Off-market window = [winEnd, winEnd + 12h]. Pre (04:00) and regular (09:30-16:00)
    // are before winEnd (~18:45) and clamp to 0. After-close extends to 20:00 ET,
    // which is inside the off-market window, so the tail of after-hours is visible.
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: date,
      window: { start: b.winEnd, end: b.winEnd + WINDOW_MS },
    })
    const pre = layout.regions.find((r) => r.kind === "pre")!
    const regular = layout.regions.find((r) => r.kind === "regular")!
    const after = layout.regions.find((r) => r.kind === "after")!
    expect(pre.x1).toBeLessThanOrEqual(pre.x0 + 1)     // pre clamped to left edge
    expect(regular.x1).toBeLessThanOrEqual(regular.x0 + 1) // regular clamped to left edge
    expect(after.x1).toBeGreaterThan(after.x0)          // after-hours tail visible
  })

  test("market window: regions span normally (market session visible)", () => {
    const b = sessionBounds(date, rule)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: date,
      window: { start: b.winStart, end: b.winEnd },
    })
    const reg = layout.regions.find((r) => r.kind === "regular")!
    expect(reg.x1).toBeGreaterThan(reg.x0)
  })

  test("ticks cover the view window range, not session range", () => {
    const b = sessionBounds(date, rule)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 200, etDate: date,
      window: { start: b.winEnd, end: b.winEnd + WINDOW_MS },
    })
    for (const tick of layout.ticks) {
      expect(tick.x).toBeGreaterThanOrEqual(0)
      expect(tick.x).toBeLessThanOrEqual(199)
    }
    // At least 11 hourly ticks in a 12h view
    expect(layout.ticks.length).toBeGreaterThanOrEqual(11)
  })

  test("markers in off-market window are placed (not dropped)", () => {
    const b = sessionBounds(date, rule)
    // Marker at the off-market midpoint
    const ms = b.winEnd + WINDOW_MS / 2
    const layout = computeLayout({
      turns: [turn(new Date(ms).toISOString())],
      interventions: [], barWidth: 100, etDate: date,
      window: { start: b.winEnd, end: b.winEnd + WINDOW_MS },
    })
    expect(layout.markers.length).toBe(1)
    expect(layout.markers[0]!.offscreen).toBe(0)
  })

  test("viewRange reflects the view window", () => {
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: date,
      window: { start: 1_000_000_000, end: 1_000_000_000 + WINDOW_MS },
    })
    expect(layout.viewRange.start).toBe(1_000_000_000)
    expect(layout.viewRange.end).toBe(1_000_000_000 + WINDOW_MS)
  })
})

// ──────────── F55: "데이마켓" / overnight session band ────────────
// The overnight session = [after_close(D), pre_open(D+1)] (20:00 ET → next-day 04:00 ET),
// crossing ET midnight. The critic-found defect: deriving it from the view-midpoint date
// alone makes the live band 0-width during exactly the hours it should show. The fix emits
// BOTH the previous- and current-evening spans; whichever is in view renders.
describe("F55 overnight (데이마켓) session", () => {
  const rule = DEFAULT_MARKET_RULE
  const date = "2026-06-01"

  // E1: overnight boundaries straddle ET midnight (close is the *next* calendar date).
  test("E1: sessionBounds overnight boundaries cross midnight", () => {
    const b = sessionBounds(date, rule)
    // current evening: 20:00 ET 06-01 → 04:00 ET 06-02
    expect(new Date(b.afterClose).toISOString()).toBe("2026-06-02T00:00:00.000Z")    // 20:00 EDT
    expect(new Date(b.overnightClose).toISOString()).toBe("2026-06-02T08:00:00.000Z") // 04:00 EDT 06-02
    expect(b.overnightClose).toBeGreaterThan(b.afterClose)
    expect(b.overnightClose - b.afterClose).toBe(8 * 60 * 60 * 1000) // 20:00 → 04:00 = 8h
    // previous evening: 20:00 ET 05-31 → close == this date's 04:00 pre-open
    expect(b.overnightPrevOpen).toBeLessThan(b.preOpen)
    expect(b.preOpen - b.overnightPrevOpen).toBe(8 * 60 * 60 * 1000)
  })

  // E2: DST — 04:00/20:00 overnight boundaries round-trip on transition days.
  const readBackEt = (ms: number) =>
    new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(ms))
  test("E2: overnight boundaries round-trip across DST", () => {
    for (const d of ["2026-03-08", "2026-11-01", "2026-06-01"]) {
      const b = sessionBounds(d, rule)
      expect(readBackEt(b.afterClose)).toBe("20:00")
      expect(readBackEt(b.overnightClose)).toBe("04:00")
      expect(readBackEt(b.overnightPrevOpen)).toBe("20:00")
    }
  })

  // E3: phaseAt classifies both overnight spans (already covered above; assert directly).
  test("E3: phaseAt returns 'day' for both evening spans", () => {
    const b = sessionBounds(date, rule)
    const at = (etDate: string, hhmm: string) => phaseAt(b, etWallToEpoch(etDate, hhmm, ET))
    expect(at("2026-06-01", "22:00")).toBe("day") // this evening
    expect(at("2026-06-02", "02:00")).toBe("day") // ...into next morning (current span)
    expect(at("2026-06-01", "02:00")).toBe("day") // previous evening's span this morning
    expect(at("2026-06-01", "04:00")).toBe("pre") // overnight closes at 04:00 → pre
  })

  // E4 (★critic HIGH): the live overnight band must actually RENDER in the off-market window
  // that the operator sees at, e.g., 02:00 ET — derived from the view-midpoint date alone it
  // was 0-width. Reproduce the real live geometry and assert width > 0.
  test("E4: overnight band renders in the post-midnight off-market window", () => {
    // now = 02:00 ET 06-02; the live tile is the off-market window containing it.
    const now = etWallToEpoch("2026-06-02", "02:00", ET)
    const liveStart = liveWindowStart(now, "2026-06-02", rule)
    const primaryEtDate = etDateOf((liveStart + liveStart + WINDOW_MS) / 2, ET)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: primaryEtDate,
      window: { start: liveStart, end: liveStart + WINDOW_MS }, now,
    })
    const dayBands = layout.regions.filter((r) => r.kind === "day" && r.x1 > r.x0)
    expect(dayBands.length).toBe(1)            // exactly one evening's span is in view
    expect(dayBands[0]!.x1 - dayBands[0]!.x0).toBeGreaterThan(10) // and it's a wide band, not a sliver
    // the live badge phase is "day" too
    expect(phaseAt(layout.bounds, now)).toBe("day")
  })

  // E4b: the NEXT off-market window (22:00 ET) shows the current-evening span.
  test("E4b: overnight band renders in the pre-midnight off-market window", () => {
    const now = etWallToEpoch(date, "22:00", ET)
    const liveStart = liveWindowStart(now, date, rule)
    const primaryEtDate = etDateOf((liveStart + liveStart + WINDOW_MS) / 2, ET)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: primaryEtDate,
      window: { start: liveStart, end: liveStart + WINDOW_MS }, now,
    })
    const dayBands = layout.regions.filter((r) => r.kind === "day" && r.x1 > r.x0)
    expect(dayBands.length).toBe(1)
    expect(phaseAt(layout.bounds, now)).toBe("day")
  })

  // E4c: in the market (regular-session-centered) window, BOTH overnight spans are 0-width.
  test("E4c: overnight bands are not drawn in the market window", () => {
    const b = sessionBounds(date, rule)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: date,
      window: { start: b.winStart, end: b.winEnd },
    })
    const dayBands = layout.regions.filter((r) => r.kind === "day" && r.x1 > r.x0)
    expect(dayBands.length).toBe(0)
  })

  // E5: month/year rollover via shiftDate (reused helper).
  test("E5: overnight derivation crosses month boundary", () => {
    const b = sessionBounds("2026-01-31", rule)
    // next-day pre-open is 2026-02-01 04:00 ET
    expect(etDateOf(b.overnightClose, ET)).toBe("2026-02-01")
    // prev-day after-close is 2026-01-30 20:00 ET
    expect(etDateOf(b.overnightPrevOpen, ET)).toBe("2026-01-30")
  })

  // E6 (regression): the DAY band is rendered like pre/after — band + label, no boundary glyph.
  test("E6: DAY label appears for a wide overnight band", () => {
    const now = etWallToEpoch("2026-06-02", "02:00", ET)
    const liveStart = liveWindowStart(now, "2026-06-02", rule)
    const primaryEtDate = etDateOf((liveStart + liveStart + WINDOW_MS) / 2, ET)
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: primaryEtDate,
      window: { start: liveStart, end: liveStart + WINDOW_MS }, now,
    })
    const cells = labelCells(layout.regions, 100, phaseShort)
    expect(cells.filter((c) => c.kind === "day").map((c) => c.ch).join("")).toBe("DAY")
  })
})
