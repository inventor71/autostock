// F86 — mobile dashboard read endpoint pure-core tests.
//   - example-based (PBT-10): full snapshot, empty/missing files, broken JSON, short side
//   - property-based (PBT): never-throw assembly (P1), position preservation (P2), return_pct
//     sign (P3), resolveSteeringDir total + priority (P5)
import { describe, expect, test } from "bun:test"
import fc from "fast-check"

import {
  assembleDashboardPayload,
  EMPTY_PAYLOAD,
  resolveSteeringDir,
  type RawSteering,
} from "../src/server/autostock/dashboard-read"

describe("assembleDashboardPayload — examples (PBT-10)", () => {
  test("full snapshot → real fields, day_pnl_pct/buying_power null (v1)", () => {
    const p = assembleDashboardPayload({
      snapshot: {
        account: { equity: 100_000, cash: 25_000, open_pnl: 1_234, position_count: 2 },
        positions: {
          AAPL: { qty: 10, avg_entry_price: 100, current_price: 110, side: "long", market_value: 1100, unrealized_pnl: 100 },
          TSLA: { qty: 5, avg_entry_price: 200, current_price: 180, side: "long", market_value: 900, unrealized_pnl: -100 },
        },
        market_open: true,
        published_at: "2026-06-16T14:29:58Z", // the snapshot's own freshness stamp
      },
      health: { status: "ok" },
      monitor: {
        ts: "2026-06-16T14:30:00Z",
        market: { phase: "regular", name: "정규장" },
        current_turn: { type: "research" },
        decisions: [{ ts: "2026-06-16T14:00:00Z", action: "BUY", symbol: "AAPL", summary: "breakout" }],
      },
      pending: [{ id: "x" }],
      snapshotMtimeIso: "2026-06-16T14:29:55Z",
    })
    expect(p.account.equity).toBe(100_000)
    expect(p.account.cash).toBe(25_000)
    expect(p.account.day_pnl_pct).toBeNull()
    expect(p.account.buying_power).toBeNull()
    expect(p.account.position_count).toBe(2)
    expect(p.positions.length).toBe(2)
    expect(p.positions.find((r) => r.symbol === "AAPL")?.return_pct).toBeCloseTo(10)
    expect(p.health).toMatchObject({ status: "ok", ok: true })
    expect(p.pending_approvals).toBe(1)
    expect(p.market).toEqual({ open: true, phase: "regular", label: "정규장" })
    expect(p.agent.current).toBe("research")
    expect(p.agent.recent[0]).toMatchObject({ action: "BUY", symbol: "AAPL" })
    // freshness anchored to the snapshot's own stamp, NOT monitor.ts (see staleness test below)
    expect(p.published_at).toBe("2026-06-16T14:29:58Z")
  })

  test("published_at is the SNAPSHOT's freshness, not monitor.ts — a frozen snapshot is not masked fresh", () => {
    // Snapshot stamp frozen at 14:00 (publish_snapshot stopped writing); monitor still ticking at 14:30.
    const stale = assembleDashboardPayload({
      snapshot: { account: { equity: 1 }, published_at: "2026-06-16T14:00:00Z" },
      monitor: { ts: "2026-06-16T14:30:00Z" },
    })
    expect(stale.published_at).toBe("2026-06-16T14:00:00Z") // monitor.ts must NOT win

    // No snapshot stamp → fall back to the snapshot file mtime (still not monitor.ts).
    const viaMtime = assembleDashboardPayload({
      snapshot: { account: { equity: 1 } },
      monitor: { ts: "2026-06-16T14:30:00Z" },
      snapshotMtimeIso: "2026-06-16T14:05:00Z",
    })
    expect(viaMtime.published_at).toBe("2026-06-16T14:05:00Z")

    // Neither stamp nor mtime → null (client treats as stale), even though monitor.ts exists.
    const none = assembleDashboardPayload({ monitor: { ts: "2026-06-16T14:30:00Z" } })
    expect(none.published_at).toBeNull()
  })

  test("position_count == returned positions length (single source of truth, even if account disagrees)", () => {
    const p = assembleDashboardPayload({
      snapshot: {
        account: { position_count: 99 }, // stale/wrong account count must not win
        positions: { AAPL: { avg_entry_price: 1, current_price: 1, side: "long" } },
      },
    })
    expect(p.account.position_count).toBe(1)
    expect(p.positions.length).toBe(1)
  })

  test("all sources missing → empty payload, published_at null (stale)", () => {
    const p = assembleDashboardPayload({})
    expect(p).toEqual(EMPTY_PAYLOAD)
    expect(p.published_at).toBeNull()
  })

  test("broken/typo-corrupt inputs → no throw, degrade to null/empty", () => {
    const p = assembleDashboardPayload({
      snapshot: "not-an-object" as unknown,
      health: 42 as unknown,
      monitor: [1, 2, 3] as unknown,
      pending: "nope" as unknown,
    })
    expect(p.account.equity).toBeNull()
    expect(p.positions).toEqual([])
    expect(p.health).toBeNull()
    expect(p.pending_approvals).toBe(0)
    expect(p.market).toBeNull()
    expect(p.published_at).toBeNull()
  })

  test("short position → return_pct positive when price falls", () => {
    const p = assembleDashboardPayload({
      snapshot: {
        positions: { SPY: { avg_entry_price: 100, current_price: 90, side: "short", market_value: -900, unrealized_pnl: 100 } },
      },
    })
    expect(p.positions[0]!.side).toBe("short")
    expect(p.positions[0]!.return_pct).toBeCloseTo(10)
  })

  test("real health.json shape (overall, not status) → mapped to {status,ok}", () => {
    // The daemon publishes health with `overall: "OK"|"WARN"|"ERROR"` + a big dimensions blob.
    const ok = assembleDashboardPayload({ health: { overall: "OK", summary: "all good", dimensions: { a: 1 } } })
    expect(ok.health).toEqual({ status: "ok", ok: true, summary: "all good" })
    const err = assembleDashboardPayload({ health: { overall: "ERROR", summary: "process(ERROR)", dimensions: {} } })
    expect(err.health).toEqual({ status: "error", ok: false, summary: "process(ERROR)" })
    // the big per-dimension blob must NOT be passed through
    expect((err.health as Record<string, unknown>).dimensions).toBeUndefined()
  })

  test("monitor.market absent but market_open present → {open} only", () => {
    const p = assembleDashboardPayload({ snapshot: { market_open: false } })
    expect(p.market).toEqual({ open: false })
  })

  test("pending falls back to snapshot.pending length", () => {
    const p = assembleDashboardPayload({ snapshot: { pending: [{}, {}, {}] } })
    expect(p.pending_approvals).toBe(3)
  })
})

// arbitrary JSON-ish value, incl. adversarial nesting/types
const jsonish: fc.Arbitrary<unknown> = fc.letrec((tie) => ({
  v: fc.oneof(
    fc.constant(null),
    fc.boolean(),
    fc.double(),
    fc.string(),
    fc.array(tie("v"), { maxLength: 4 }),
    fc.dictionary(fc.string(), tie("v"), { maxKeys: 4 }),
  ),
})).v

describe("assembleDashboardPayload — properties", () => {
  test("P1: never throws and returns a schema-valid payload for ANY input", () => {
    fc.assert(
      fc.property(jsonish, jsonish, jsonish, jsonish, (snapshot, health, monitor, pending) => {
        const p = assembleDashboardPayload({ snapshot, health, monitor, pending } as RawSteering)
        expect(Array.isArray(p.positions)).toBe(true)
        expect(Number.isInteger(p.pending_approvals) && p.pending_approvals >= 0).toBe(true)
        expect(p.account.position_count >= 0).toBe(true)
        expect(typeof p.agent.current === "string" || p.agent.current === null).toBe(true)
        expect(Array.isArray(p.agent.recent)).toBe(true)
      }),
    )
  })

  test("P2: positions length & symbols preserved from snapshot.positions dict", () => {
    const positionArb = fc.record({
      avg_entry_price: fc.double({ min: 1, max: 1000, noNaN: true }),
      current_price: fc.double({ min: 1, max: 1000, noNaN: true }),
      side: fc.constantFrom("long", "short"),
      market_value: fc.double({ min: -1000, max: 1000, noNaN: true }),
      unrealized_pnl: fc.double({ min: -500, max: 500, noNaN: true }),
    })
    fc.assert(
      fc.property(fc.dictionary(fc.string({ minLength: 1 }), positionArb, { maxKeys: 8 }), (posDict) => {
        const p = assembleDashboardPayload({ snapshot: { positions: posDict } })
        expect(p.positions.length).toBe(Object.keys(posDict).length)
        expect(new Set(p.positions.map((r) => r.symbol))).toEqual(new Set(Object.keys(posDict)))
      }),
    )
  })

  test("P3: return_pct sign follows side; avg=0/invalid → null", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1000, noNaN: true }),
        fc.double({ min: 1, max: 1000, noNaN: true }),
        fc.constantFrom("long", "short"),
        (avg, cur, side) => {
          const p = assembleDashboardPayload({
            snapshot: { positions: { X: { avg_entry_price: avg, current_price: cur, side } } },
          })
          const rp = p.positions[0]!.return_pct
          if (cur === avg) {
            expect(rp).toBeCloseTo(0)
          } else {
            const up = cur > avg
            const expectPositive = side === "long" ? up : !up
            expect((rp ?? 0) > 0).toBe(expectPositive)
          }
        },
      ),
    )
    // avg = 0 → null (no division blowup)
    const z = assembleDashboardPayload({ snapshot: { positions: { X: { avg_entry_price: 0, current_price: 5, side: "long" } } } })
    expect(z.positions[0]!.return_pct).toBeNull()
  })
})

describe("resolveSteeringDir — properties (P5)", () => {
  test("total: returns string|null for any env/cwd, never throws", () => {
    fc.assert(
      fc.property(
        fc.dictionary(fc.string(), fc.string(), { maxKeys: 5 }),
        fc.string(),
        (env, cwd) => {
          const r = resolveSteeringDir(env, cwd)
          expect(r === null || typeof r === "string").toBe(true)
        },
      ),
    )
  })

  test("priority: STEERING_DIR wins when it exists (use a real dir)", () => {
    // process.cwd() exists as a directory → STEERING_DIR pointing at it must win.
    const r = resolveSteeringDir({ STEERING_DIR: process.cwd(), AUTOSTOCK_ROOT: "/nonexistent" }, "/nonexistent")
    expect(r).toBe(process.cwd())
  })

  test("all candidates missing → null", () => {
    const r = resolveSteeringDir({ STEERING_DIR: "/no/such/a", AUTOSTOCK_ROOT: "/no/such/b" }, "/no/such/c")
    expect(r).toBeNull()
  })
})
