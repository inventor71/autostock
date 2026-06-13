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
