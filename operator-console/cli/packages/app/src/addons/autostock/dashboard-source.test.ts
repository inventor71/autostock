// F86 — client dashboard-source pure mappers + fetch.
//   - example-based (PBT-10): mapping, weightPct, market phase, fetch failure → null
//   - property-based: positions preserved (P2), round-trip never-throws (P6), isStale
//     fail-safe revalidation (P4)
import { describe, expect, test } from "bun:test"
import fc from "fast-check"

import {
  fetchDashboard,
  toMarket,
  toPositionRows,
  toSnapshotSources,
  type DashboardPayload,
} from "./dashboard-source"
import { buildDashboard, isStale } from "./snapshot"

function payload(over: Partial<DashboardPayload> = {}): DashboardPayload {
  return {
    account: { equity: 100, cash: 20, day_pnl_pct: null, buying_power: null, open_pnl: 5, position_count: 2 },
    positions: [
      { symbol: "AAPL", market_value: 600, unrealized_pnl: 60, return_pct: 11.1, side: "long", current_price: 110 },
      { symbol: "TSLA", market_value: 400, unrealized_pnl: -20, return_pct: -5, side: "long", current_price: 180 },
    ],
    health: { status: "ok" },
    pending_approvals: 1,
    market: { open: true, phase: "regular", label: "정규장" },
    agent: { current: "research", recent: [{ action: "BUY", symbol: "AAPL" }] },
    published_at: "2026-06-16T14:30:00Z",
    ...over,
  }
}

describe("toSnapshotSources / toPositionRows / toMarket — examples", () => {
  test("payload → SnapshotSources drives a non-offline dashboard model", () => {
    const m = buildDashboard(toSnapshotSources(payload()))
    expect(m.offline).toBe(false)
    expect(m.equity).toBe(100)
    expect(m.positionCount).toBe(2)
    expect(m.symbols).toEqual(["AAPL", "TSLA"])
    expect(m.pendingApprovals).toBe(1)
    expect(m.asOf).toBe("2026-06-16T14:30:00Z")
  })

  test("weightPct = share of total absolute market value", () => {
    const rows = toPositionRows(payload().positions)
    expect(rows.find((r) => r.symbol === "AAPL")?.weightPct).toBeCloseTo(60)
    expect(rows.find((r) => r.symbol === "TSLA")?.weightPct).toBeCloseTo(40)
    expect(rows[0]!.dayPct).toBe(11.1) // return_pct carried through
  })

  test("weightPct null when total is zero (no divide-by-zero)", () => {
    const rows = toPositionRows([
      { symbol: "X", market_value: 0, unrealized_pnl: 0, return_pct: null, side: "long", current_price: 1 },
    ])
    expect(rows[0]!.weightPct).toBeNull()
  })

  test("toMarket maps explicit phase, else derives from open bool, else undefined", () => {
    expect(toMarket({ open: true, phase: "pre" })).toEqual({ phase: "pre", label: undefined })
    expect(toMarket({ open: true })).toEqual({ phase: "regular", label: undefined })
    expect(toMarket({ open: false })).toEqual({ phase: "closed", label: undefined })
    expect(toMarket({ open: null })).toBeUndefined()
    expect(toMarket(null)).toBeUndefined()
  })
})

describe("fetchDashboard", () => {
  const http = { url: "https://pc.ts.net", username: "u", password: "p" }

  test("returns parsed payload on 200", async () => {
    const fakeFetch = (async () => new Response(JSON.stringify(payload()), { status: 200 })) as unknown as typeof fetch
    const p = await fetchDashboard(http, fakeFetch)
    expect(p?.account.equity).toBe(100)
  })

  test("non-200 → null", async () => {
    const fakeFetch = (async () => new Response("nope", { status: 500 })) as unknown as typeof fetch
    expect(await fetchDashboard(http, fakeFetch)).toBeNull()
  })

  test("network throw → null (offline, no stale hold)", async () => {
    const fakeFetch = (async () => {
      throw new Error("offline")
    }) as unknown as typeof fetch
    expect(await fetchDashboard(http, fakeFetch)).toBeNull()
  })

  test("sends basic-auth header", async () => {
    let seen: string | null = null
    const fakeFetch = (async (_url: string, init: RequestInit) => {
      seen = (init.headers as Record<string, string>).authorization ?? null
      return new Response(JSON.stringify(payload()), { status: 200 })
    }) as unknown as typeof fetch
    await fetchDashboard(http, fakeFetch)
    expect(seen).toMatch(/^Basic /)
  })
})

const positionArb = fc.record({
  symbol: fc.string({ minLength: 1 }),
  market_value: fc.option(fc.double({ min: -1e6, max: 1e6, noNaN: true }), { nil: null }),
  unrealized_pnl: fc.option(fc.double({ noNaN: true }), { nil: null }),
  return_pct: fc.option(fc.double({ noNaN: true }), { nil: null }),
  side: fc.constantFrom("long" as const, "short" as const),
  current_price: fc.option(fc.double({ noNaN: true }), { nil: null }),
})

describe("properties", () => {
  test("P2: toPositionRows preserves count & symbols", () => {
    fc.assert(
      fc.property(fc.array(positionArb, { maxLength: 12 }), (positions) => {
        const rows = toPositionRows(positions)
        expect(rows.length).toBe(positions.length)
        expect(rows.map((r) => r.symbol)).toEqual(positions.map((p) => p.symbol))
        for (const r of rows) expect(r.weightPct == null || r.weightPct >= 0).toBe(true)
      }),
    )
  })

  test("P6: toSnapshotSources∘buildDashboard never throws; equity is number|null", () => {
    const accountArb = fc.record({
      equity: fc.option(fc.double({ noNaN: true }), { nil: null }),
      cash: fc.option(fc.double({ noNaN: true }), { nil: null }),
      day_pnl_pct: fc.option(fc.double({ noNaN: true }), { nil: null }),
      buying_power: fc.constant(null),
      open_pnl: fc.option(fc.double({ noNaN: true }), { nil: null }),
      position_count: fc.nat({ max: 50 }),
    })
    const payloadArb = fc.record({
      account: accountArb,
      positions: fc.array(positionArb, { maxLength: 10 }),
      health: fc.option(fc.record({ status: fc.string() }), { nil: null }),
      pending_approvals: fc.nat({ max: 20 }),
      market: fc.constant(null),
      agent: fc.constant({ current: null, recent: [] }),
      published_at: fc.option(fc.string(), { nil: null }),
    }) as fc.Arbitrary<DashboardPayload>
    fc.assert(
      fc.property(payloadArb, (p) => {
        const m = buildDashboard(toSnapshotSources(p))
        expect(m.equity === null || typeof m.equity === "number").toBe(true)
        expect(m.dayPnlPct === null || typeof m.dayPnlPct === "number").toBe(true)
        expect(typeof m.offline).toBe("boolean")
      }),
    )
  })

  test("P4: isStale is fail-safe — true when offline, no asOf, unparseable, or past threshold", () => {
    const offline = buildDashboard(toSnapshotSources(payload({ published_at: null })))
    expect(isStale(offline, Date.now(), 30_000)).toBe(true) // no asOf → stale

    const fresh = buildDashboard(toSnapshotSources(payload({ published_at: new Date().toISOString() })))
    expect(isStale(fresh, Date.now(), 30_000)).toBe(false)
    // same model, far in the future "now" → stale
    expect(isStale(fresh, Date.now() + 60_000, 30_000)).toBe(true)

    fc.assert(
      fc.property(fc.string(), (bad) => {
        const m = buildDashboard(toSnapshotSources(payload({ published_at: bad })))
        // unparseable timestamp must never read as fresh
        if (Number.isNaN(Date.parse(bad))) expect(isStale(m, Date.now(), 30_000)).toBe(true)
      }),
    )
  })
})
