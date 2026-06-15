import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterAll, afterEach, beforeEach, describe, expect, it } from "vitest";

import { appRouter } from "@/server/routers/_app";

/** Fixture repo root with daemon-shaped artifacts. */
const root = mkdtempSync(path.join(os.tmpdir(), "viz-router-"));
afterAll(() => rmSync(root, { recursive: true, force: true }));

function seedFixture() {
  mkdirSync(path.join(root, "steering"), { recursive: true });
  mkdirSync(path.join(root, "workspace", "positions"), { recursive: true });
  writeFileSync(
    path.join(root, "steering", "snapshot.json"),
    JSON.stringify({
      account: { equity: 100, cash: 50 },
      positions: { RTX: { qty: 19 } },
    }),
  );
  const day = 86_400_000;
  const rec = (daysAgo: number) =>
    JSON.stringify({ ts: new Date(Date.now() - daysAgo * day).toISOString(), equity: 100 - daysAgo });
  writeFileSync(
    path.join(root, "workspace", "equity.jsonl"),
    [rec(40), rec(10), rec(1)].map((l) => `${l}\n`).join(""),
  );
  writeFileSync(path.join(root, "workspace", "positions", "RTX.md"), "# RTX thesis\nbody");
  writeFileSync(path.join(root, "workspace", "positions", "BRK.B.md"), "# BRK.B");
  writeFileSync(path.join(root, "workspace", "positions", "notes.txt"), "ignored");
  // Tier 1 jsonl artifacts (chronological append; newest last).
  writeFileSync(
    path.join(root, "workspace", "decisions.jsonl"),
    [
      JSON.stringify({ ts: "2026-06-13T10:00:00-04:00", symbol: "RTX", action: "HOLD", confidence: 0.7, stop: 175.5, target: 210, reason: "first" }),
      JSON.stringify({ ts: "2026-06-13T11:00:00-04:00", symbol: "TMO", action: "BUY", confidence: 0.6, reason: "second" }),
    ].map((l) => `${l}\n`).join(""),
  );
  writeFileSync(
    path.join(root, "workspace", "turns.jsonl"),
    [
      JSON.stringify({ turn_id: "W1", ts: "2026-06-13T09:00:00+09:00", turn_type: "wake", model: "sonnet", cost_usd: 0.35, input_tokens: 3, output_tokens: 297, summary: "s1" }),
      JSON.stringify({ turn_id: "R1", ts: "2026-06-13T10:00:00+09:00", turn_type: "research", cost_usd: 1.2 }),
    ].map((l) => `${l}\n`).join(""),
  );
  writeFileSync(
    path.join(root, "workspace", "trades.jsonl"),
    JSON.stringify({ symbol: "AAPL", qty: 10, entry_price: 309, exit_price: 298.79, realized_pnl: -102.14, return_pct: -3.31, closed_at: "2026-06-09T13:34:29Z" }) + "\n",
  );
  // Tier 2: quality (dated dir), health (steering), watchlist/regime (md).
  mkdirSync(path.join(root, "workspace", "quality"), { recursive: true });
  writeFileSync(
    path.join(root, "workspace", "quality", "2026-06-12.json"),
    JSON.stringify({ total_outcomes: 1, direction_hit_rate: { total: 1, hits: 0, rate: 0 } }),
  );
  writeFileSync(
    path.join(root, "workspace", "quality", "2026-06-13.json"),
    JSON.stringify({
      total_outcomes: 22,
      direction_hit_rate: { total: 6, hits: 0, rate: 0 },
      target_quality: { reached_count: 0, total: 22, reach_rate: 0 },
      realized_rr: { mean: 0, count: 0 },
      confidence_calibration: { "0.51-0.7": { count: 6, hits: 0, rate: 0 } },
    }),
  );
  writeFileSync(
    path.join(root, "steering", "health.json"),
    JSON.stringify({
      overall: "ERROR",
      ts: "2026-06-14T10:47:00Z",
      dimensions: {
        resources: { dimension: "resources", status: "OK", checks: [{ name: "disk_space", status: "OK", detail: "ok" }] },
        account: { dimension: "account", status: "ERROR", checks: [{ name: "broker", status: "ERROR", detail: "down" }] },
      },
    }),
  );
  writeFileSync(path.join(root, "workspace", "watchlist.md"), "# Watchlist\nbody");
  writeFileSync(path.join(root, "workspace", "regime.md"), "# Regime\nbody");
}

const caller = appRouter.createCaller({});
let prevRoot: string | undefined;

beforeEach(() => {
  prevRoot = process.env.AUTOSTOCK_ROOT;
  process.env.AUTOSTOCK_ROOT = root;
  seedFixture();
});
afterEach(() => {
  if (prevRoot === undefined) delete process.env.AUTOSTOCK_ROOT;
  else process.env.AUTOSTOCK_ROOT = prevRoot;
});

describe("structural read-only guarantee (BR-6)", () => {
  it("every procedure in the app router is a query — zero mutations", () => {
    const procedures = appRouter._def.procedures as unknown as Record<
      string,
      { _def: { type: string } }
    >;
    const entries = Object.entries(procedures);
    expect(entries.length).toBeGreaterThan(0);
    for (const [name, proc] of entries) {
      expect(proc._def.type, `${name} must be a query`).toBe("query");
    }
  });
});

describe("portfolio.snapshot", () => {
  it("returns the parsed snapshot", async () => {
    const snap = await caller.portfolio.snapshot();
    expect(snap?.account?.equity).toBe(100);
    expect(snap?.positions["RTX"].qty).toBe(19);
  });

  it("returns null when the snapshot file is missing (BR-8)", async () => {
    rmSync(path.join(root, "steering", "snapshot.json"));
    expect(await caller.portfolio.snapshot()).toBeNull();
  });
});

describe("portfolio.equity", () => {
  it("filters records by sinceDays window", async () => {
    const out = await caller.portfolio.equity({ sinceDays: 30 });
    expect(out).toHaveLength(2); // 40-days-ago record excluded
  });

  it("defaults to a 30-day window", async () => {
    const out = await caller.portfolio.equity();
    expect(out).toHaveLength(2);
  });

  it.each([[0], [366], [1.5]])("rejects sinceDays=%s (zod)", async (sinceDays) => {
    await expect(caller.portfolio.equity({ sinceDays })).rejects.toThrow();
  });

  it("returns [] when the file is missing", async () => {
    rmSync(path.join(root, "workspace", "equity.jsonl"));
    expect(await caller.portfolio.equity({ sinceDays: 30 })).toEqual([]);
  });
});

describe("portfolio.listPositions", () => {
  it("lists only valid SYMBOL.md files, sorted", async () => {
    expect(await caller.portfolio.listPositions()).toEqual(["BRK.B", "RTX"]);
  });

  it("returns [] when the directory is missing", async () => {
    rmSync(path.join(root, "workspace", "positions"), { recursive: true });
    expect(await caller.portfolio.listPositions()).toEqual([]);
  });
});

describe("portfolio.thesis (BR-7 double whitelist)", () => {
  it("returns opaque markdown for a real position", async () => {
    const doc = await caller.portfolio.thesis({ symbol: "RTX" });
    expect(doc?.markdown).toContain("# RTX thesis");
    expect(doc?.stale).toBe(false);
  });

  it("returns null for a symbol without a thesis file", async () => {
    expect(await caller.portfolio.thesis({ symbol: "MSFT" })).toBeNull();
  });

  it.each([["../etc"], ["rtx"], ["A/B"], ["A".repeat(11)], [""]])(
    "rejects malformed symbol %j at the schema layer",
    async (symbol) => {
      await expect(caller.portfolio.thesis({ symbol })).rejects.toThrow();
    },
  );
});

describe("Tier 1 jsonl tail procedures (decisions/turns/trades)", () => {
  it("decisions tail returns parsed rows with reason narrative", async () => {
    const rows = await caller.portfolio.decisions({ limit: 50 });
    expect(rows).toHaveLength(2);
    expect(rows[1].action).toBe("BUY");
    expect(rows[0].reason).toBe("first");
    expect(rows[0].stop).toBe(175.5);
  });

  it("turns tail exposes cost/tokens/type", async () => {
    const rows = await caller.portfolio.turns({ limit: 50 });
    expect(rows).toHaveLength(2);
    expect(rows[0].cost_usd).toBe(0.35);
    expect(rows[0].turn_type).toBe("wake");
  });

  it("trades tail returns closed round trips", async () => {
    const rows = await caller.portfolio.trades({ limit: 50 });
    expect(rows).toHaveLength(1);
    expect(rows[0].realized_pnl).toBe(-102.14);
    expect(rows[0].return_pct).toBe(-3.31);
  });

  it("limit caps the tail window (newest kept)", async () => {
    const rows = await caller.portfolio.decisions({ limit: 1 });
    expect(rows).toHaveLength(1);
    expect(rows[0].symbol).toBe("TMO"); // newest
  });

  it.each([[0], [501], [1.5]])("rejects limit=%s (zod)", async (limit) => {
    await expect(caller.portfolio.decisions({ limit })).rejects.toThrow();
  });

  it("returns [] when a jsonl file is missing (fail-honest)", async () => {
    rmSync(path.join(root, "workspace", "trades.jsonl"));
    expect(await caller.portfolio.trades({ limit: 50 })).toEqual([]);
  });
});

describe("Tier 2 (quality/health/watchlist/regime)", () => {
  it("quality returns the LATEST dated file", async () => {
    const out = await caller.portfolio.quality();
    expect(out?.date).toBe("2026-06-13"); // newest of the two
    expect(out?.metrics.total_outcomes).toBe(22);
    expect(out?.metrics.direction_hit_rate?.total).toBe(6);
  });

  it("quality returns null when the dir is missing", async () => {
    rmSync(path.join(root, "workspace", "quality"), { recursive: true });
    expect(await caller.portfolio.quality()).toBeNull();
  });

  it("health parses overall + dimensions (dict keyed)", async () => {
    const h = await caller.portfolio.health();
    expect(h?.overall).toBe("ERROR");
    expect(h?.dimensions["account"].status).toBe("ERROR");
    expect(h?.dimensions["resources"].checks[0].name).toBe("disk_space");
  });

  it("health returns null when absent", async () => {
    rmSync(path.join(root, "steering", "health.json"));
    expect(await caller.portfolio.health()).toBeNull();
  });

  it("watchlist/regime return opaque markdown", async () => {
    expect((await caller.portfolio.watchlist())?.markdown).toContain("# Watchlist");
    expect((await caller.portfolio.regime())?.markdown).toContain("# Regime");
    expect((await caller.portfolio.watchlist())?.stale).toBe(false);
  });

  it("watchlist returns null when absent", async () => {
    rmSync(path.join(root, "workspace", "watchlist.md"));
    expect(await caller.portfolio.watchlist()).toBeNull();
  });
});
