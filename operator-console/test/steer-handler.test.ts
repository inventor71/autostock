import { afterEach, beforeEach, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FileDrop } from "../src/filedrop";
import { handleSteer, handleSteerRead } from "../src/steer-handler";

// The MCP server's tool logic. Confirm is opencode's MCP auto-gate (verified live via
// bun dev); these cover the deterministic parse+(read|write) the handlers own.
let dir: string;
let fd: FileDrop;
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "mcp-"));
  fd = new FileDrop(dir, "tok");
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

function verbs(): string[] {
  try {
    return readFileSync(fd.commandsFile, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l).verb);
  } catch {
    return [];
  }
}

test("handleSteer: mutating command writes confirmed+token", () => {
  expect(handleSteer("/sell AAPL 50%", fd)).toContain("OK sell");
  expect(verbs()).toEqual(["sell"]);
});

test("handleSteer: read verb routed to steer_read, no write", () => {
  expect(handleSteer("/status", fd)).toContain("steer_read");
  expect(verbs()).toEqual([]);
});

test("handleSteer: malformed rejected, no write", () => {
  expect(handleSteer("/buy AAPL 1000", fd)).toContain("rejected");
  expect(verbs()).toEqual([]);
});

test("handleSteer: no token -> write disabled", () => {
  const fd2 = new FileDrop(dir, "");
  expect(handleSteer("/pause", fd2)).toContain("token missing");
  expect(verbs()).toEqual([]);
});

test("handleSteerRead: returns snapshot, never writes", () => {
  writeFileSync(fd.snapshotFile, JSON.stringify({ run_state: { paused: false }, positions: {} }));
  expect(handleSteerRead("/status", fd)).toContain("snapshot");
  expect(verbs()).toEqual([]);
});

test("handleSteerRead: mutating command routed to steer (with confirm), no write", () => {
  expect(handleSteerRead("/sell AAPL 50%", fd)).toContain("use the steer tool");
  expect(verbs()).toEqual([]);
});
