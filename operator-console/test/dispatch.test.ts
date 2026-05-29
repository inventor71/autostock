import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Dispatcher } from "../src/dispatch";
import { FileDrop } from "../src/filedrop";

// Directly unit-tests the SHARED confirm/dispatch state machine (review #5) — the
// exact logic the real TuiPlugin will reuse, not a stub-only copy.
let dir: string;
let out: string[];
let d: Dispatcher;
let fd: FileDrop;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "disp-"));
  out = [];
  fd = new FileDrop(dir, "tok");
  d = new Dispatcher(fd, { write: (s) => out.push(s) });
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

function written(): string[] {
  try {
    return readFileSync(fd.commandsFile, "utf8").trim().split("\n").filter(Boolean)
      .map((l) => JSON.parse(l).verb);
  } catch {
    return [];
  }
}

test("confirm flow: await then y -> sent", () => {
  expect(d.handle("/pause").kind).toBe("await_confirm");
  expect(d.awaitingConfirm()).toBe(true);
  expect(d.handle("y").kind).toBe("sent");
  expect(d.awaitingConfirm()).toBe(false);
  expect(written()).toEqual(["pause"]);
});

test("destructive needs CONFIRM; plain 'y' / 'n' cancels (no write)", () => {
  d.handle("/flatten all");
  expect(d.handle("y").kind).toBe("cancelled"); // 'y' is NOT enough for destructive
  expect(written()).toEqual([]);
  d.handle("/flatten all");
  expect(d.handle("CONFIRM").kind).toBe("sent");
  expect(written()).toEqual(["flatten_all"]);
});

test("a new command typed at the confirm prompt cancels (no-op), never executes either", () => {
  d.handle("/sell AAPL 50%"); // pending
  const r = d.handle("/buy MSFT 100sh"); // not 'y' -> cancelled
  expect(r.kind).toBe("cancelled");
  expect(written()).toEqual([]); // neither the sell nor the buy executed (fail-closed)
});

test("read-only verb: no write, no confirm", () => {
  expect(d.handle("/status").kind).toBe("read");
  expect(d.awaitingConfirm()).toBe(false);
  expect(written()).toEqual([]);
});

test("note applies without confirm", () => {
  expect(d.handle("/note watch CPI").kind).toBe("sent");
  expect(written()).toEqual(["note"]);
});

test("parse error: no write, pending cleared", () => {
  d.handle("/sell AAPL 50%"); // pending
  // resolve pending first (cancel), then a malformed command errors cleanly
  d.handle("n");
  const r = d.handle("/buy AAPL 1000"); // no unit
  expect(r.kind).toBe("error");
  expect(d.awaitingConfirm()).toBe(false);
  expect(written()).toEqual([]);
});

test("no token -> send path errors, nothing written", () => {
  const fd2 = new FileDrop(dir, "");
  const d2 = new Dispatcher(fd2, { write: () => {} });
  d2.handle("/pause");
  expect(d2.handle("y").kind).toBe("error"); // NoTokenError surfaced, not written
  expect(written()).toEqual([]);
});
