// F79 C2 — SnapshotController tests: example-based (PBT-10) + property-based (PBT-03).
import { describe, expect, test } from "bun:test"
import fc from "fast-check"

import { assembleSnapshot, buildDashboard, isStale } from "./snapshot"

describe("assembleSnapshot / buildDashboard (FR-2)", () => {
  test("full sources → populated dashboard model", () => {
    const m = buildDashboard({
      account: { equity: 12_340, day_pnl_pct: 1.24 },
      positions: [{ symbol: "AAPL" }, { symbol: "TSLA" }],
      health: { status: "ok" },
      pendingApprovals: 1,
      publishedAt: "2026-06-13T14:00:00Z",
    })
    expect(m.offline).toBe(false)
    expect(m.equity).toBe(12_340)
    expect(m.dayPnlPct).toBe(1.24)
    expect(m.positionCount).toBe(2)
    expect(m.symbols).toEqual(["AAPL", "TSLA"])
    expect(m.healthOk).toBe(true)
    expect(m.pendingApprovals).toBe(1)
    expect(m.asOf).toBe("2026-06-13T14:00:00Z")
  })

  test("empty sources → safe zero/null model, not offline", () => {
    const m = buildDashboard({})
    expect(m.offline).toBe(false)
    expect(m.positionCount).toBe(0)
    expect(m.symbols).toEqual([])
    expect(m.pendingApprovals).toBe(0)
    expect(m.healthOk).toBe(null)
  })

  test("offline opt → offline model regardless of sources", () => {
    const m = buildDashboard({ account: { equity: 1 } }, { offline: true })
    expect(m.offline).toBe(true)
  })

  // Regression from PBT counterexample [{}]: positionCount counts ALL positions
  // (toDashboard uses positions.length) while symbols lists only string-symbol ones —
  // a symbol-less position diverges the two. Pin that behavior so it stays intentional.
  test("symbol-less position → positionCount counts it, symbols omits it", () => {
    const m = buildDashboard({ positions: [{ symbol: "AAPL" }, {}] })
    expect(m.positionCount).toBe(2)
    expect(m.symbols).toEqual(["AAPL"])
  })
})

describe("buildDashboard — PBT-03 invariants (never-throw, counts, pending)", () => {
  const sources = fc.record(
    {
      account: fc.option(
        fc.record(
          { equity: fc.option(fc.double(), { nil: null }), day_pnl_pct: fc.option(fc.double(), { nil: null }) },
          { requiredKeys: [] },
        ),
        { nil: null },
      ),
      positions: fc.option(
        fc.array(fc.record({ symbol: fc.option(fc.string(), { nil: null }) }, { requiredKeys: [] })),
        { nil: null },
      ),
      health: fc.option(fc.record({ status: fc.string(), ok: fc.boolean() }, { requiredKeys: [] }), { nil: null }),
      pendingApprovals: fc.nat(),
      publishedAt: fc.option(fc.string(), { nil: null }),
    },
    { requiredKeys: [] },
  )

  test("never throws + position counts coherent + pending preserved + not offline", () => {
    fc.assert(
      fc.property(sources, (s) => {
        const m = buildDashboard(s)
        const total = (s.positions ?? []).length
        const validSymbols = (s.positions ?? []).filter((p) => typeof p?.symbol === "string").length
        // invariant: positionCount = total positions; symbols = only string-symbol ones (⊆)
        expect(m.positionCount).toBe(total)
        expect(m.symbols.length).toBe(validSymbols)
        expect(m.symbols.length).toBeLessThanOrEqual(m.positionCount)
        // invariant: pending count round-trips when a number was supplied
        expect(m.pendingApprovals).toBe(s.pendingApprovals ?? 0)
        // invariant: assembled-from-sources path is never offline
        expect(m.offline).toBe(false)
      }),
      { numRuns: 300 },
    )
  })
})

describe("isStale (NFR-7 fail-safe)", () => {
  const NOW = Date.parse("2026-06-13T14:00:10Z")
  test("offline → stale", () => {
    expect(isStale(buildDashboard({}, { offline: true }), NOW, 15_000)).toBe(true)
  })
  test("no asOf → stale", () => {
    expect(isStale(buildDashboard({ account: { equity: 1 } }), NOW, 15_000)).toBe(true)
  })
  test("fresh asOf within threshold → not stale", () => {
    const m = buildDashboard({ publishedAt: "2026-06-13T14:00:05Z" })
    expect(isStale(m, NOW, 15_000)).toBe(false)
  })
  test("old asOf beyond threshold → stale", () => {
    const m = buildDashboard({ publishedAt: "2026-06-13T13:00:00Z" })
    expect(isStale(m, NOW, 15_000)).toBe(true)
  })
  test("unparseable asOf → stale (fail-safe)", () => {
    const m = buildDashboard({ publishedAt: "not-a-date" })
    expect(isStale(m, NOW, 15_000)).toBe(true)
  })

  test("PBT: a missing/old/bad snapshot is never reported fresh", () => {
    fc.assert(
      fc.property(fc.option(fc.string(), { nil: null }), fc.integer({ min: 0, max: 1e12 }), (asOf, now) => {
        const m = buildDashboard({ publishedAt: asOf })
        const stale = isStale(m, now, 15_000)
        const t = asOf ? Date.parse(asOf) : NaN
        if (Number.isNaN(t) || now - t > 15_000) expect(stale).toBe(true)
      }),
      { numRuns: 300 },
    )
  })
})
