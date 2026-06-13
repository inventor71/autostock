import { describe, expect, it } from "vitest";

import { POST as resetPost } from "@/app/api/chat/reset/route";
import { releaseTurn, tryAcquireTurn, isTurnInFlight } from "@/server/chat/turn-lock";

describe("POST /api/chat/reset vs in-flight turn (race guard)", () => {
  it("refuses with 409 while a turn is in flight", async () => {
    expect(tryAcquireTurn()).toBe(true);
    try {
      const res = await resetPost();
      expect(res.status).toBe(409);
    } finally {
      releaseTurn();
    }
  });

  it("resets when idle", async () => {
    expect(isTurnInFlight()).toBe(false);
    const res = await resetPost();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });

  it("turn lock is single-flight and re-acquirable after release", () => {
    expect(tryAcquireTurn()).toBe(true);
    expect(tryAcquireTurn()).toBe(false);
    releaseTurn();
    expect(tryAcquireTurn()).toBe(true);
    releaseTurn();
  });
});
