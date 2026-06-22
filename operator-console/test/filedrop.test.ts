import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FileDrop, NoTokenError } from "../src/filedrop";
import type { SteeringCommand } from "../src/schema";

let dir: string;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "fd-")); });
afterEach(() => {
  // Clean up the shared workspace/positions directory (derived from steeringDir
  // as join(steeringDir, "..", "workspace", "positions") which is shared when
  // steeringDir is a temp path).
  try { rmSync(join(dir, "..", "workspace"), { recursive: true, force: true }); } catch {}
  rmSync(dir, { recursive: true, force: true });
});

test("build attaches token + confirmed + human source + hex id", () => {
  const fd = new FileDrop(dir, "tok-123");
  const cmd = fd.build("pause", {});
  expect(cmd).toMatchObject({ verb: "pause", confirmed: true, token: "tok-123", source: "human" });
  expect(cmd.id).toMatch(/^[0-9a-f]{32}$/); // uuid4 hex, no dashes (matches Unit A)
  expect(typeof cmd.ts).toBe("string");
});

test("no token -> write disabled (NoTokenError)", () => {
  const fd = new FileDrop(dir, "");
  expect(fd.hasToken()).toBe(false);
  expect(() => fd.build("kill", {})).toThrow(NoTokenError);
});

test("send appends a round-trippable JSON line", () => {
  const fd = new FileDrop(dir, "tok");
  const id = fd.send("sell", { symbol: "AAPL", size: 50, unit: "%" });
  const lines = readFileSync(fd.commandsFile, "utf8").trim().split("\n");
  expect(lines).toHaveLength(1);
  const parsed = JSON.parse(lines[0]) as SteeringCommand;
  expect(parsed.id).toBe(id);
  expect(parsed).toMatchObject({ verb: "sell", confirmed: true, token: "tok", source: "human", args: { symbol: "AAPL", size: 50, unit: "%" } });
});

test("readEvents is torn-safe (withholds an incomplete trailing line)", () => {
  const fd = new FileDrop(dir, "tok");
  const e1 = JSON.stringify({ id: "1", corr_id: "c1", ts: "t", kind: "outcome", payload: { outcome: "executed" } });
  const e2 = JSON.stringify({ id: "2", corr_id: null, ts: "t", kind: "fill", payload: {} });
  writeFileSync(fd.eventsFile, e1 + "\n" + e2.slice(0, 10)); // 2nd line torn
  const r1 = fd.readEvents(0);
  expect(r1.events.map((e) => e.id)).toEqual(["1"]); // torn 2nd withheld
  // complete the 2nd line; next read from the saved offset picks up only it
  writeFileSync(fd.eventsFile, e1 + "\n" + e2 + "\n");
  const r2 = fd.readEvents(r1.offset);
  expect(r2.events.map((e) => e.id)).toEqual(["2"]);
});

test("readSnapshot parses or returns null", () => {
  const fd = new FileDrop(dir, "tok");
  expect(fd.readSnapshot()).toBeNull(); // absent
  writeFileSync(fd.snapshotFile, JSON.stringify({ run_state: { paused: false }, positions: {} }));
  expect(fd.readSnapshot()).toMatchObject({ run_state: { paused: false } });
});

// F53: position thesis file reads
test("readThesis returns null for missing file, content for existing", () => {
  const fd = new FileDrop(dir, "tok");
  expect(fd.readThesis("UNKNOWN")).toBeNull(); // no file
  // create workspace/positions/AAPL.md
  mkdirSync(fd.positionsDir, { recursive: true });
  writeFileSync(join(fd.positionsDir, "AAPL.md"), "# AAPL Thesis\n\nBuy thesis here.", "utf8");
  expect(fd.readThesis("aapl")).toBe("# AAPL Thesis\n\nBuy thesis here."); // lowercased symbol ok
});

// F76: stat-stable read returns the complete, untorn thesis. A torn read can only
// occur when a write straddles the read; that interleaving isn't reproducible in
// single-threaded JS, so we assert the invariant the fix preserves — readThesis
// returns the exact full bytes for a settled file (no truncation) and reflects the
// latest write after a rewrite.
test("readThesis returns full content and reflects rewrites (stat-stable)", () => {
  const fd = new FileDrop(dir, "tok");
  mkdirSync(fd.positionsDir, { recursive: true });
  const big = "# AAPL Thesis\n" + "x".repeat(64 * 1024) + "\nend";
  writeFileSync(join(fd.positionsDir, "AAPL.md"), big, "utf8");
  expect(fd.readThesis("AAPL")).toBe(big); // complete, not truncated
  writeFileSync(join(fd.positionsDir, "AAPL.md"), "# rewritten\nshorter", "utf8");
  expect(fd.readThesis("AAPL")).toBe("# rewritten\nshorter"); // latest write
});

test("listTheses returns symbols or empty", () => {
  // Ensure clean state — afterEach cleans workspace/ but be defensive.
  try { rmSync(join(dir, "..", "workspace"), { recursive: true, force: true }); } catch {}
  const fd = new FileDrop(dir, "tok");
  expect(fd.listTheses()).toEqual([]); // no dir yet
  mkdirSync(fd.positionsDir, { recursive: true });
  writeFileSync(join(fd.positionsDir, "AAPL.md"), "...", "utf8");
  writeFileSync(join(fd.positionsDir, "MSFT.md"), "...", "utf8");
  writeFileSync(join(fd.positionsDir, "notes.txt"), "not a thesis", "utf8"); // non-.md ignored
  expect(fd.listTheses()).toEqual(["AAPL", "MSFT"]); // sorted
});
