import { expect, test, describe } from "bun:test"
import { windowedCost } from "../src/utils/format"

// F58: windowed cost = sum of cost_usd for turns whose ts ∈ [start, end).
describe("windowedCost (F58)", () => {
  const ms = (iso: string) => Date.parse(iso)
  const start = ms("2026-06-03T20:00:00-04:00")
  const end = ms("2026-06-04T08:00:00-04:00") // 12h window

  const turn = (iso: string, cost: number) => ({ ts: iso, cost_usd: cost })

  test("empty turns → 0", () => {
    expect(windowedCost([], start, end)).toBe(0)
  })

  test("sums only turns inside the window", () => {
    const turns = [
      turn("2026-06-03T21:00:00-04:00", 0.5), // in
      turn("2026-06-04T02:30:00-04:00", 1.25), // in
      turn("2026-06-04T07:59:59-04:00", 0.25), // in (just before end)
    ]
    expect(windowedCost(turns, start, end)).toBeCloseTo(2.0, 6)
  })

  test("excludes turns before the window start", () => {
    const turns = [turn("2026-06-03T19:59:59-04:00", 9.9)] // 1s before start
    expect(windowedCost(turns, start, end)).toBe(0)
  })

  test("end is exclusive (half-open)", () => {
    const turns = [turn("2026-06-04T08:00:00-04:00", 9.9)] // exactly end
    expect(windowedCost(turns, start, end)).toBe(0)
  })

  test("start is inclusive", () => {
    const turns = [turn("2026-06-03T20:00:00-04:00", 3.3)] // exactly start
    expect(windowedCost(turns, start, end)).toBeCloseTo(3.3, 6)
  })

  test("mixes in/out turns (multi-date window) and sums only the in ones", () => {
    const turns = [
      turn("2026-06-03T12:00:00-04:00", 5.0), // before (prev session)
      turn("2026-06-03T22:00:00-04:00", 1.0), // in (06-03 evening)
      turn("2026-06-04T06:00:00-04:00", 2.0), // in (06-04 morning)
      turn("2026-06-04T12:00:00-04:00", 4.0), // after (next window)
    ]
    expect(windowedCost(turns, start, end)).toBeCloseTo(3.0, 6)
  })

  test("unparseable ts is skipped (not NaN-poisoned)", () => {
    const turns = [
      turn("not-a-date", 9.9),
      turn("2026-06-04T01:00:00-04:00", 1.5), // in
    ]
    expect(windowedCost(turns, start, end)).toBeCloseTo(1.5, 6)
  })

  test("missing/zero cost contributes 0", () => {
    const turns = [
      { ts: "2026-06-04T01:00:00-04:00", cost_usd: 0 },
      { ts: "2026-06-04T02:00:00-04:00", cost_usd: NaN as unknown as number },
    ]
    // 0 + (NaN || 0) → 0
    expect(windowedCost(turns, start, end)).toBe(0)
  })
})
