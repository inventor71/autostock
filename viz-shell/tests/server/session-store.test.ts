import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterAll, describe, expect, it } from "vitest";

import { SessionStore } from "@/server/chat/session-store";

const tmp = mkdtempSync(path.join(os.tmpdir(), "viz-session-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

describe("SessionStore (BR-14)", () => {
  it("returns null when no session file exists", () => {
    expect(new SessionStore(path.join(tmp, "none", "session.json")).id).toBeNull();
  });

  it("persists and reads back an id (creates parent dirs)", () => {
    const store = new SessionStore(path.join(tmp, "a", "session.json"));
    store.set("sess-123");
    expect(store.id).toBe("sess-123");
    expect(new SessionStore(path.join(tmp, "a", "session.json")).id).toBe("sess-123");
  });

  it("reset removes the session (idempotent)", () => {
    const store = new SessionStore(path.join(tmp, "b", "session.json"));
    store.set("sess-x");
    store.reset();
    expect(store.id).toBeNull();
    store.reset(); // second reset must not throw
  });

  it("returns null for a corrupt file instead of throwing", () => {
    const p = path.join(tmp, "corrupt.json");
    writeFileSync(p, "{not json");
    expect(new SessionStore(p).id).toBeNull();
  });
});
