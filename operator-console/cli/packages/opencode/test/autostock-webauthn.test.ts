// F71 U2 + F75 hardening — security gate pure-core tests (no crypto, no Effect):
// mutating classification (fail-closed), origin classification (in-process / host-local /
// remote incl. tailscale-serve loopback hop), gate decision matrix, value-keyed single-use
// challenge TTL, constant-time basic-auth check, https-only origin.
import { describe, expect, test } from "bun:test"

import {
  CHALLENGE_MAX,
  CHALLENGE_TTL_MS,
  checkBasicAuth,
  consumeChallenge,
  decideGate,
  expectedOrigin,
  expectedRpId,
  extractClientChallenge,
  isLoopbackAddress,
  isMutatingAutostockPermission,
  isRemoteOrigin,
  issueChallenge,
  promptNeedsAssertion,
  checkPrompt,
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
  test("undefined is NOT loopback — in-process is classified separately", () => {
    expect(isLoopbackAddress(undefined)).toBe(false)
  })
  test("tailnet/remote addresses are not loopback", () => {
    expect(isLoopbackAddress("100.101.102.103")).toBe(false)
    expect(isLoopbackAddress("::ffff:100.101.102.103")).toBe(false)
  })
})

describe("isRemoteOrigin (F75)", () => {
  test("in-process (no socket) is local", () => {
    expect(isRemoteOrigin(undefined, false)).toBe(false)
    expect(isRemoteOrigin(undefined, true)).toBe(false) // header alone can't make in-process remote
  })
  test("plain loopback (attach-mode TUI, host-local) is local", () => {
    expect(isRemoteOrigin("127.0.0.1", false)).toBe(false)
  })
  test("loopback WITH tailscale identity header = tailscale-serve hop = REMOTE", () => {
    expect(isRemoteOrigin("127.0.0.1", true)).toBe(true)
  })
  test("non-loopback socket is remote regardless of header", () => {
    expect(isRemoteOrigin("100.1.2.3", false)).toBe(true)
    expect(isRemoteOrigin("100.1.2.3", true)).toBe(true)
  })
})

describe("decideGate", () => {
  const base = {
    reply: "once" as const,
    remoteAddress: "100.1.2.3",
    tailscaleIdentity: false,
    permission: "autostock_cancel_all_orders",
  }
  test("remote mutating approve without assertion → denied", () => {
    expect(decideGate({ ...base, assertionValid: false })).toContain("WebAuthn")
  })
  test("remote mutating approve WITH valid assertion → allowed", () => {
    expect(decideGate({ ...base, assertionValid: true })).toBeNull()
  })
  test("reject is always allowed (no signature to refuse)", () => {
    expect(decideGate({ ...base, reply: "reject", assertionValid: false })).toBeNull()
  })
  test("host-local loopback approve bypasses (attach-mode TUI)", () => {
    expect(decideGate({ ...base, remoteAddress: "127.0.0.1", assertionValid: false })).toBeNull()
    expect(decideGate({ ...base, remoteAddress: undefined, assertionValid: false })).toBeNull()
  })
  test("F75: loopback via tailscale-serve proxy (identity header) is GATED", () => {
    expect(
      decideGate({ ...base, remoteAddress: "127.0.0.1", tailscaleIdentity: true, assertionValid: false }),
    ).toContain("WebAuthn")
    expect(
      decideGate({ ...base, remoteAddress: "127.0.0.1", tailscaleIdentity: true, assertionValid: true }),
    ).toBeNull()
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

describe("challenge store (value-keyed, F75)", () => {
  test("single-use: consume removes", () => {
    issueChallenge("assert", 1000, "abc")
    expect(consumeChallenge("assert", "abc", 1001)).toBe(true)
    expect(consumeChallenge("assert", "abc", 1001)).toBe(false)
  })
  test("expired challenge is rejected", () => {
    issueChallenge("assert", 1000, "exp")
    expect(consumeChallenge("assert", "exp", 1000 + CHALLENGE_TTL_MS + 1)).toBe(false)
  })
  test("wrong kind is rejected (and consumed — single use either way)", () => {
    issueChallenge("register", 1000, "regonly")
    expect(consumeChallenge("assert", "regonly", 1001)).toBe(false)
    expect(consumeChallenge("register", "regonly", 1001)).toBe(false)
  })
  test("F75: two in-flight challenges don't invalidate each other", () => {
    issueChallenge("assert", 1000, "first")
    issueChallenge("assert", 1000, "second")
    expect(consumeChallenge("assert", "first", 1001)).toBe(true)
    expect(consumeChallenge("assert", "second", 1001)).toBe(true)
  })
  test("unknown/null value is rejected", () => {
    expect(consumeChallenge("assert", "never-issued", 1001)).toBe(false)
    expect(consumeChallenge("assert", null, 1001)).toBe(false)
  })
  test("F75: capped at CHALLENGE_MAX — oldest evicted, memory bounded", () => {
    for (let i = 0; i < CHALLENGE_MAX + 10; i++) issueChallenge("assert", 5000, `c${i}`)
    expect(consumeChallenge("assert", "c0", 5001)).toBe(false) // evicted
    expect(consumeChallenge("assert", `c${CHALLENGE_MAX + 9}`, 5001)).toBe(true) // newest survives
  })
})

describe("extractClientChallenge (F75)", () => {
  const wrap = (clientData: unknown) => ({
    response: { clientDataJSON: Buffer.from(JSON.stringify(clientData)).toString("base64url") },
  })
  test("pulls the base64url challenge out of clientDataJSON", () => {
    expect(extractClientChallenge(wrap({ type: "webauthn.get", challenge: "abc123" }))).toBe("abc123")
  })
  test("garbage/missing → null", () => {
    expect(extractClientChallenge({})).toBeNull()
    expect(extractClientChallenge({ response: { clientDataJSON: "%%%" } })).toBeNull()
    expect(extractClientChallenge(wrap({ challenge: 42 }))).toBeNull()
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

// F79 S1 — remote session-prompt gate (agent steering = mutating).
describe("promptNeedsAssertion (F79 S1)", () => {
  test("in-process (no socket) does not need assertion", () => {
    expect(promptNeedsAssertion(undefined, false)).toBe(false)
    expect(promptNeedsAssertion(undefined, true)).toBe(false)
  })
  test("host-local loopback (attach-mode TUI) does not need assertion", () => {
    expect(promptNeedsAssertion("127.0.0.1", false)).toBe(false)
  })
  test("loopback via tailscale-serve hop (phone) needs assertion", () => {
    expect(promptNeedsAssertion("127.0.0.1", true)).toBe(true)
  })
  test("non-loopback socket needs assertion", () => {
    expect(promptNeedsAssertion("100.1.2.3", false)).toBe(true)
  })
})

describe("checkPrompt (F79 S1)", () => {
  const cfg = { env: { AUTOSTOCK_WEBAUTHN_ORIGIN: "https://pc.tail.ts.net" } }
  test("local origin → pass through (null), no crypto required", async () => {
    expect(await checkPrompt({ remoteAddress: "127.0.0.1", tailscaleUserLogin: undefined, header: undefined }, cfg)).toBeNull()
    expect(await checkPrompt({ remoteAddress: undefined, tailscaleUserLogin: undefined, header: undefined }, cfg)).toBeNull()
  })
  test("remote without assertion (WebAuthn configured) → denied (fail-closed)", async () => {
    const denial = await checkPrompt({ remoteAddress: "100.1.2.3", tailscaleUserLogin: undefined, header: undefined }, cfg)
    expect(denial).not.toBeNull()
    expect(denial).toContain("WebAuthn")
  })
  test("remote via tailscale hop without assertion → denied", async () => {
    const denial = await checkPrompt(
      { remoteAddress: "127.0.0.1", tailscaleUserLogin: "alice@example.com", header: undefined },
      cfg,
    )
    expect(denial).not.toBeNull()
    expect(denial).toContain("WebAuthn")
  })
  test("remote but WebAuthn NOT configured → pass through (no dead-lock on plain serve)", async () => {
    expect(
      await checkPrompt({ remoteAddress: "100.1.2.3", tailscaleUserLogin: undefined, header: undefined }, { env: {} }),
    ).toBeNull()
  })
})
