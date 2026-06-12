// F71 U3 — client logic: QR pairing parse, WebAuthn ceremony serialization, dashboard model.
import { describe, expect, test } from "bun:test"

import { parsePairingPayload } from "./pairing"
import { b64urlToBuf, obtainAssertionHeader, optionsToRequest, WebAuthnError } from "./webauthn-client"
import { dashboardSummary, EMPTY_DASHBOARD, toDashboard } from "./dashboard"

describe("parsePairingPayload (US-1)", () => {
  const good = JSON.stringify({ v: 1, kind: "autostock-pair", url: "http://100.1.2.3:4096", password: "pw" })
  test("valid payload → http ServerConnection with url+password", () => {
    const r = parsePairingPayload(good)
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.server.type).toBe("http")
      expect(r.server.http.url).toBe("http://100.1.2.3:4096")
      expect(r.server.http.password).toBe("pw")
    }
  })
  test("rejects non-JSON", () => {
    expect(parsePairingPayload("not json").ok).toBe(false)
  })
  test("rejects wrong kind", () => {
    expect(parsePairingPayload(JSON.stringify({ v: 1, kind: "other", url: "http://x", password: "p" })).ok).toBe(false)
  })
  test("rejects unsupported version", () => {
    expect(parsePairingPayload(JSON.stringify({ v: 2, kind: "autostock-pair", url: "http://x", password: "p" })).ok).toBe(false)
  })
  test("rejects missing password / bad url", () => {
    expect(parsePairingPayload(JSON.stringify({ v: 1, kind: "autostock-pair", url: "http://x", password: "" })).ok).toBe(false)
    expect(parsePairingPayload(JSON.stringify({ v: 1, kind: "autostock-pair", url: "ftp://x", password: "p" })).ok).toBe(false)
  })
})

describe("webauthn-client (US-5)", () => {
  test("b64url roundtrip", () => {
    const buf = new Uint8Array([1, 2, 3, 250, 255]).buffer
    const s = btoa(String.fromCharCode(1, 2, 3, 250, 255)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "")
    expect(new Uint8Array(b64urlToBuf(s))).toEqual(new Uint8Array(buf))
  })

  test("optionsToRequest decodes challenge + allowCredentials, defaults UV=required", () => {
    const req = optionsToRequest({ challenge: "YWJj", allowCredentials: [{ id: "YWJj" }] })
    expect(req.userVerification).toBe("required")
    expect(new Uint8Array(req.challenge as ArrayBuffer)).toEqual(new Uint8Array([97, 98, 99]))
    expect(req.allowCredentials?.[0]?.type).toBe("public-key")
  })

  test("obtainAssertionHeader: options → credentials.get → base64(JSON) header", async () => {
    const fetcher = async () =>
      new Response(JSON.stringify({ challenge: "YWJj", rpId: "pc.ts.net", allowCredentials: [{ id: "YWJj" }] }), {
        status: 200,
      })
    const fakeCred = {
      id: "cred1",
      type: "public-key",
      rawId: new Uint8Array([1]).buffer,
      response: {
        authenticatorData: new Uint8Array([2]).buffer,
        clientDataJSON: new Uint8Array([3]).buffer,
        signature: new Uint8Array([4]).buffer,
        userHandle: null,
      },
    } as unknown as Credential
    const header = await obtainAssertionHeader({
      fetcher,
      credentialsGet: async () => fakeCred,
    })
    const decoded = JSON.parse(atob(header))
    expect(decoded.id).toBe("cred1")
    expect(decoded.response.signature).toBeTruthy()
  })

  test("obtainAssertionHeader: user cancel → WebAuthnError", async () => {
    const fetcher = async () => new Response(JSON.stringify({ challenge: "YWJj" }), { status: 200 })
    await expect(
      obtainAssertionHeader({ fetcher, credentialsGet: async () => null }),
    ).rejects.toBeInstanceOf(WebAuthnError)
  })

  test("obtainAssertionHeader: options error → WebAuthnError", async () => {
    const fetcher = async () => new Response(JSON.stringify({ error: "no passkey" }), { status: 400 })
    await expect(
      obtainAssertionHeader({ fetcher, credentialsGet: async () => null }),
    ).rejects.toBeInstanceOf(WebAuthnError)
  })
})

describe("dashboard model (US-2)", () => {
  test("offline / non-object → empty offline model", () => {
    expect(toDashboard(null).offline).toBe(true)
    expect(toDashboard({}, { offline: true }).offline).toBe(true)
    expect(toDashboard("nope").positionCount).toBe(0)
  })
  test("shapes account/positions/health/pending", () => {
    const snap = {
      account: { equity: 105000, day_pnl_pct: 1.23 },
      positions: [{ symbol: "NVDA" }, { symbol: "TSLA" }],
      health: { status: "ok" },
      pending_approvals: [{ id: "p1" }],
      published_at: "2026-06-11T14:00:00Z",
    }
    const m = toDashboard(snap)
    expect(m.offline).toBe(false)
    expect(m.equity).toBe(105000)
    expect(m.dayPnlPct).toBe(1.23)
    expect(m.positionCount).toBe(2)
    expect(m.symbols).toEqual(["NVDA", "TSLA"])
    expect(m.healthOk).toBe(true)
    expect(m.pendingApprovals).toBe(1)
    expect(m.asOf).toBe("2026-06-11T14:00:00Z")
  })
  test("unknown health → null (not false)", () => {
    expect(toDashboard({ account: {} }).healthOk).toBeNull()
  })
  test("unhealthy → false", () => {
    expect(toDashboard({ health: { status: "degraded" } }).healthOk).toBe(false)
  })
  test("summary lines", () => {
    expect(dashboardSummary(EMPTY_DASHBOARD)).toContain("오프라인")
    const s = dashboardSummary(toDashboard({ account: { equity: 1000, day_pnl_pct: -2 }, health: { ok: true }, pending_approvals: [1] }))
    expect(s).toContain("포지션 0")
    expect(s).toContain("승인대기 1")
    expect(s).toContain("-2.00%")
  })
})
