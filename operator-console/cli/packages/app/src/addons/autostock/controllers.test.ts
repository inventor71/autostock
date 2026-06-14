// F79 C4/C9 — controller core tests (queue reduction + inactivity lock).
import { describe, expect, test } from "bun:test"
import fc from "fast-check"

import { badgeCount, nextForSheet, selectPending, type PendingApproval } from "./approval-queue"
import { DEFAULT_LOCK_TIMEOUT_MS, msUntilLock, shouldLock } from "./lock"
import { basicAuthHeader, joinUrl } from "./webauthn-fetch"

describe("ApprovalQueue (C4, FR-6)", () => {
  const a: PendingApproval = { id: "a", permission: "autostock_place_stock_order" }
  const b: PendingApproval = { id: "b", permission: "autostock_close_position" }

  test("badge counts distinct pending, excludes dismissed", () => {
    expect(badgeCount([a, b], new Set())).toBe(2)
    expect(badgeCount([a, b], new Set(["a"]))).toBe(1)
    expect(badgeCount([a, b], new Set(["a", "b"]))).toBe(0)
  })

  test("nextForSheet is arrival order, skips dismissed, null when empty", () => {
    expect(nextForSheet([a, b], new Set())?.id).toBe("a")
    expect(nextForSheet([a, b], new Set(["a"]))?.id).toBe("b")
    expect(nextForSheet([a, b], new Set(["a", "b"]))).toBeNull()
  })

  test("de-dups repeated ids and ignores id-less entries", () => {
    const dupe = [a, a, { id: "" } as PendingApproval, b]
    expect(selectPending(dupe, new Set()).map((x) => x.id)).toEqual(["a", "b"])
  })

  test("PBT: badgeCount == selectPending length, never exceeds distinct ids", () => {
    const item = fc.record({ id: fc.string(), permission: fc.option(fc.string(), { nil: undefined }) })
    fc.assert(
      fc.property(fc.array(item), fc.array(fc.string()), (items, dismissedArr) => {
        const dismissed = new Set(dismissedArr)
        const pending = selectPending(items, dismissed)
        expect(badgeCount(items, dismissed)).toBe(pending.length)
        const distinct = new Set(items.filter((i) => i.id && !dismissed.has(i.id)).map((i) => i.id))
        expect(pending.length).toBe(distinct.size)
      }),
      { numRuns: 300 },
    )
  })
})

describe("LockController (C9, NFR-6)", () => {
  test("default timeout is 5 minutes", () => {
    expect(DEFAULT_LOCK_TIMEOUT_MS).toBe(300_000)
  })

  test("locks at/after timeout, not before", () => {
    expect(shouldLock(1_000, 1_000 + 299_999, DEFAULT_LOCK_TIMEOUT_MS)).toBe(false)
    expect(shouldLock(1_000, 1_000 + 300_000, DEFAULT_LOCK_TIMEOUT_MS)).toBe(true)
    expect(shouldLock(1_000, 1_000 + 400_000, DEFAULT_LOCK_TIMEOUT_MS)).toBe(true)
  })

  test("zero timeout locks immediately", () => {
    expect(shouldLock(5_000, 5_000, 0)).toBe(true)
  })

  test("msUntilLock counts down to 0, never negative", () => {
    expect(msUntilLock(0, 0, 300_000)).toBe(300_000)
    expect(msUntilLock(0, 100_000, 300_000)).toBe(200_000)
    expect(msUntilLock(0, 999_999, 300_000)).toBe(0)
  })

  test("PBT: shouldLock(t) iff msUntilLock(t) === 0", () => {
    fc.assert(
      fc.property(fc.nat(), fc.nat(), fc.integer({ min: 0, max: 600_000 }), (last, delta, timeout) => {
        const now = last + delta
        expect(shouldLock(last, now, timeout)).toBe(msUntilLock(last, now, timeout) === 0)
      }),
      { numRuns: 300 },
    )
  })
})

describe("webauthn-fetch pure helpers", () => {
  test("basicAuthHeader = 'Basic ' + base64(user:pass), default user opencode", () => {
    expect(basicAuthHeader({ password: "pw" })).toBe("Basic " + btoa("opencode:pw"))
    expect(basicAuthHeader({ username: "alice", password: "pw" })).toBe("Basic " + btoa("alice:pw"))
    expect(basicAuthHeader({})).toBe("Basic " + btoa("opencode:"))
  })

  test("joinUrl normalizes slashes", () => {
    expect(joinUrl("http://x:4096", "/autostock/webauthn/assert-options")).toBe(
      "http://x:4096/autostock/webauthn/assert-options",
    )
    expect(joinUrl("http://x:4096/", "/p")).toBe("http://x:4096/p")
    expect(joinUrl("http://x:4096///", "p")).toBe("http://x:4096/p")
  })
})
