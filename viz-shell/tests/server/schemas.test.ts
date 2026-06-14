import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { EquityRecordSchema, SnapshotSchema } from "@/server/schemas";

describe("SnapshotSchema (E1 — verified against live snapshot shape)", () => {
  const liveShape = {
    run_state: { paused: false, entries_halted: false, et_date: "2026-06-12" },
    positions: {
      RTX: {
        qty: 19.0,
        avg_entry_price: 176.34,
        side: "long",
        current_price: 183.53,
        market_value: 3487.07,
        unrealized_pnl: 136.61,
      },
    },
    account: { equity: 99614.5, cash: 96127.43, invested: 3487.07, open_pnl: 136.61, position_count: 1 },
    market_open: false,
    published_at: "2026-06-13T05:03:28",
  };

  it("parses the live snapshot shape (positions = dict keyed by symbol)", () => {
    const out = SnapshotSchema.parse(liveShape);
    expect(out.account?.equity).toBe(99614.5);
    expect(out.positions["RTX"].qty).toBe(19);
  });

  it("passes unknown fields through (BR-9)", () => {
    const out = SnapshotSchema.parse(liveShape) as Record<string, unknown>;
    expect(out.run_state).toEqual(liveShape.run_state);
  });

  it("coerces stringy numerics in positions", () => {
    const out = SnapshotSchema.parse({ positions: { A: { qty: "3" } } });
    expect(out.positions["A"].qty).toBe(3);
  });

  it("defaults positions to {} when absent", () => {
    expect(SnapshotSchema.parse({}).positions).toEqual({});
  });

  it("parses Tier-0 fields (open_orders/recent_fills/round_trip/run_state)", () => {
    const out = SnapshotSchema.parse({
      open_orders: [
        { symbol: "TMO", order_id: "x", side: "buy", order_type: "limit", limit_price: 465, stop_price: null, current_price: 469.39 },
        { symbol: "RTX", side: "sell", order_type: "stop", limit_price: null, stop_price: 175.5, current_price: 183.53 },
      ],
      recent_fills: [{ ts: "2026-06-09T13:34:29.118658+00:00", side: "sell", qty: 2, symbol: "AAPL", price: 297.8 }],
      round_trip: { closed_count: 0, win_rate: null, realized_pnl: 0.0, as_of: "2026-06-14T02:39:07-04:00" },
      run_state: { paused: false, entries_halted: false, et_date: "2026-06-13" },
    });
    expect(out.open_orders).toHaveLength(2);
    expect(out.open_orders[0].limit_price).toBe(465);
    expect(out.open_orders[0].stop_price ?? null).toBeNull(); // nullish preserved
    expect(out.recent_fills[0].symbol).toBe("AAPL");
    expect(out.round_trip?.win_rate ?? null).toBeNull(); // null until a round trip closes
    expect(out.run_state?.et_date).toBe("2026-06-13");
  });

  it("defaults open_orders/recent_fills to [] when absent", () => {
    const out = SnapshotSchema.parse({});
    expect(out.open_orders).toEqual([]);
    expect(out.recent_fills).toEqual([]);
  });
});

describe("EquityRecordSchema (E2)", () => {
  it("parses a live-shaped line", () => {
    const out = EquityRecordSchema.parse({
      ts: "2026-06-13T05:03:28",
      equity: 99614.5,
      benchmark: { SPY: 741.77, QQQ: 721.34 },
      extra_future_field: [1, 2],
    });
    expect(out.equity).toBe(99614.5);
    expect((out as Record<string, unknown>).extra_future_field).toEqual([1, 2]);
  });

  it("rejects a record missing required fields", () => {
    expect(() => EquityRecordSchema.parse({ equity: 1 })).toThrow();
  });

  it("PBT: JSON serialization round-trip preserves the record", () => {
    fc.assert(
      fc.property(
        fc.record({
          ts: fc.date({ noInvalidDate: true }).map((d) => d.toISOString()),
          equity: fc.double({ noNaN: true, noDefaultInfinity: true }),
          extra: fc.string(),
        }),
        (rec) => {
          const parsed = EquityRecordSchema.parse(JSON.parse(JSON.stringify(rec)));
          expect(parsed.ts).toBe(rec.ts);
          expect((parsed as Record<string, unknown>).extra).toBe(rec.extra);
        },
      ),
      { numRuns: 200 },
    );
  });
});
