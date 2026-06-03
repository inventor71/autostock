import { expect, test, describe } from "bun:test"
import {
  tzOffsetMs,
  etWallToEpoch,
  sessionBounds,
  computeLayout,
  phaseAt,
  labelCells,
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

  test("three regions present and ordered", () => {
    const layout = computeLayout({
      turns: [], interventions: [], barWidth: 100, etDate: "2026-06-01",
    })
    expect(layout.regions.map((r) => r.kind)).toEqual(["pre", "regular", "after"])
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
    expect(at("03:00")).toBe("closed")  // before pre-open
    expect(at("05:00")).toBe("pre")     // pre-market
    expect(at("10:00")).toBe("regular") // regular session
    expect(at("17:00")).toBe("after")   // after-hours
    expect(at("21:00")).toBe("closed")  // after close
  })
  test("boundaries are half-open (open inclusive, close exclusive)", () => {
    expect(at("09:30")).toBe("regular")  // exactly open
    expect(at("16:00")).toBe("after")    // exactly close → after
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
