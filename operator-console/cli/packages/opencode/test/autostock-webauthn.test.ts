// F71 U2 — security gate pure-core tests (no crypto, no Effect):
// mutating classification (fail-closed), loopback detection (in-process = local),
// gate decision matrix, single-use challenge TTL, basic-auth check, https-only origin.
import { describe, expect, test } from "bun:test"

import {
  CHALLENGE_TTL_MS,
  checkBasicAuth,
  consumeChallenge,
  decideGate,
  expectedOrigin,
  expectedRpId,
  isLoopbackAddress,
  isMutatingAutostockPermission,
  issueChallenge,
} from "../src/server/autostock/webauthn"

describe("isMutatingAutostockPermission", () => {
  test("known mutating keys", () => {
    for (const k of [
      "autostock_steer",
      "autostock_place_stock_order",
      "autostock_cancel_order_by_id",
      "autostock_cancel_all_orders",
      "autostock_replace_order_by_id",
      "autostock_close_position",
      "autostock_close_all_positions",
    ]) {
      expect(isMutatingAutostockPermission(k)).toBe(true)
    }
  })
  test("read-only keys are not mutating", () => {
    for (const k of ["autostock_steer_read", "autostock_get_orders", "autostock_get_account_info"]) {
      expect(isMutatingAutostockPermission(k)).toBe(false)
    }
  })
  test("UNKNOWN autostock key fails closed (counts as mutating)", () => {
    expect(isMutatingAutostockPermission("autostock_brand_new_tool")).toBe(true)
  })
  test("non-autostock permissions are out of scope", () => {
    expect(isMutatingAutostockPermission("edit")).toBe(false)
    expect(isMutatingAutostockPermission("doom_loop")).toBe(false)
  })
})

describe("isLoopbackAddress", () => {
  test("loopback forms", () => {
    expect(isLoopbackAddress("127.0.0.1")).toBe(true)
    expect(isLoopbackAddress("::1")).toBe(true)
    expect(isLoopbackAddress("::ffff:127.0.0.1")).toBe(true)
  })
  test("undefined = in-process (desktop TUI embedded fetch) = local", () => {
    expect(isLoopbackAddress(undefined)).toBe(true)
  })
  test("tailnet/remote addresses are not loopback", () => {
    expect(isLoopbackAddress("100.101.102.103")).toBe(false)
    expect(isLoopbackAddress("::ffff:100.101.102.103")).toBe(false)
  })
})

describe("decideGate", () => {
  const base = { reply: "once" as const, remoteAddress: "100.1.2.3", permission: "autostock_cancel_all_orders" }
  test("remote mutating approve without assertion → denied", () => {
    expect(decideGate({ ...base, assertionValid: false })).toContain("WebAuthn")
  })
  test("remote mutating approve WITH valid assertion → allowed", () => {
    expect(decideGate({ ...base, assertionValid: true })).toBeNull()
  })
  test("reject is always allowed (no signature to refuse)", () => {
    expect(decideGate({ ...base, reply: "reject", assertionValid: false })).toBeNull()
  })
  test("loopback approve bypasses (desktop)", () => {
    expect(decideGate({ ...base, remoteAddress: "127.0.0.1", assertionValid: false })).toBeNull()
    expect(decideGate({ ...base, remoteAddress: undefined, assertionValid: false })).toBeNull()
  })
  test("non-autostock permission untouched", () => {
    expect(decideGate({ ...base, permission: "edit", assertionValid: false })).toBeNull()
  })
  test("pending not found → pass through (reply layer 404s)", () => {
    expect(decideGate({ ...base, permission: undefined, assertionValid: false })).toBeNull()
  })
  test("emergency/steer included — no exemption (UAQ: 모든 뮤테이팅 서명)", () => {
    expect(decideGate({ ...base, permission: "autostock_steer", assertionValid: false })).toContain("WebAuthn")
  })
})

describe("challenge store", () => {
  test("single-use: consume removes", () => {
    issueChallenge("assert", 1000, "abc")
    expect(consumeChallenge("assert", 1001)).toBe("abc")
    expect(consumeChallenge("assert", 1001)).toBeNull()
  })
  test("expired challenge is rejected", () => {
    issueChallenge("assert", 1000, "abc")
    expect(consumeChallenge("assert", 1000 + CHALLENGE_TTL_MS + 1)).toBeNull()
  })
  test("register/assert kinds are independent", () => {
    issueChallenge("register", 1000, "reg")
    issueChallenge("assert", 1000, "ast")
    expect(consumeChallenge("assert", 1001)).toBe("ast")
    expect(consumeChallenge("register", 1001)).toBe("reg")
  })
})

describe("checkBasicAuth", () => {
  const env = { OPENCODE_SERVER_PASSWORD: "pw" }
  const b64 = (s: string) => Buffer.from(s).toString("base64")
  test("correct password passes regardless of username", () => {
    expect(checkBasicAuth(`Basic ${b64("opencode:pw")}`, env)).toBe(true)
    expect(checkBasicAuth(`Basic ${b64("anything:pw")}`, env)).toBe(true)
  })
  test("wrong/missing password fails", () => {
    expect(checkBasicAuth(`Basic ${b64("opencode:nope")}`, env)).toBe(false)
    expect(checkBasicAuth(null, env)).toBe(false)
  })
  test("no configured password fails closed", () => {
    expect(checkBasicAuth(`Basic ${b64("opencode:pw")}`, {})).toBe(false)
  })
})

describe("expectedOrigin/RpId (https-only — WebAuthn secure context)", () => {
  test("https origin accepted; hostname becomes rpID", () => {
    const env = { AUTOSTOCK_WEBAUTHN_ORIGIN: "https://pc.tail1234.ts.net" }
    expect(expectedOrigin(env)).toBe("https://pc.tail1234.ts.net")
    expect(expectedRpId(env)).toBe("pc.tail1234.ts.net")
  })
  test("http origin rejected (fail-closed)", () => {
    expect(expectedOrigin({ AUTOSTOCK_WEBAUTHN_ORIGIN: "http://100.1.2.3:4096" })).toBeNull()
  })
  test("unset/garbage rejected", () => {
    expect(expectedOrigin({})).toBeNull()
    expect(expectedOrigin({ AUTOSTOCK_WEBAUTHN_ORIGIN: "not a url" })).toBeNull()
  })
})
