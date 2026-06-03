import { expect, test, describe } from "bun:test"
import { fmtElapsedClock, fmtTurnLabel } from "../src/utils/format"

describe("fmtElapsedClock (F44)", () => {
  test("sub-minute → seconds", () => {
    expect(fmtElapsedClock(0)).toBe("0s")
    expect(fmtElapsedClock(9_000)).toBe("9s")
    expect(fmtElapsedClock(59_000)).toBe("59s")
  })
  test("minutes → MmSSs with zero-padded seconds", () => {
    expect(fmtElapsedClock(60_000)).toBe("1m00s")
    expect(fmtElapsedClock(192_000)).toBe("3m12s")
    expect(fmtElapsedClock(3_599_000)).toBe("59m59s")
  })
  test("hours → HhMMm", () => {
    expect(fmtElapsedClock(3_600_000)).toBe("1h00m")
    expect(fmtElapsedClock(3_720_000)).toBe("1h02m")
  })
  test("negative clamps to 0s (clock skew safety)", () => {
    expect(fmtElapsedClock(-5_000)).toBe("0s")
  })
})

describe("fmtTurnLabel (F44)", () => {
  const start = "2026-06-03T21:42:52+09:00"
  const now = Date.parse(start) + 192_000 // +3m12s

  test("null turn → null (caller renders idle)", () => {
    expect(fmtTurnLabel(null, 0, now)).toBeNull()
  })
  test("running turn, no queue → 'type · elapsed'", () => {
    expect(fmtTurnLabel({ type: "research", started_at: start }, 0, now)).toBe(
      "research · 3m12s",
    )
  })
  test("running turn with queue → appends '+N queued'", () => {
    expect(fmtTurnLabel({ type: "research", started_at: start }, 1, now)).toBe(
      "research · 3m12s · +1 queued",
    )
    expect(fmtTurnLabel({ type: "intraday", started_at: start }, 3, now)).toBe(
      "intraday · 3m12s · +3 queued",
    )
  })
  test("queued count of 0 is omitted", () => {
    expect(fmtTurnLabel({ type: "eod", started_at: start }, 0, now)).not.toContain("queued")
  })
})
