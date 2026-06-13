// F79 C3 — SignedMutationGateway tests (PBT-10 example-based for the security-critical path):
// sign-pass attaches the header, cancel/locked fail closed (call never runs).
import { describe, expect, test } from "bun:test"

import { LockedError, WEBAUTHN_HEADER, WebAuthnError, withWebAuthn } from "./signed-mutation"

// Minimal fake authenticator: assert-options returns a challenge, credentialsGet returns a
// credential whose response serializes deterministically. Mirrors webauthn-client's shape.
function fakeDeps(opts: { cancel?: boolean; optionsStatus?: number; locked?: boolean } = {}) {
  const fetcher = async (path: string) => {
    if (path === "/autostock/webauthn/assert-options") {
      if (opts.optionsStatus && opts.optionsStatus >= 400) {
        return new Response(JSON.stringify({ error: "no passkey" }), { status: opts.optionsStatus })
      }
      return new Response(JSON.stringify({ challenge: "Y2hhbGxlbmdl" }), { status: 200 })
    }
    return new Response("{}", { status: 404 })
  }
  const credentialsGet = async () => {
    if (opts.cancel) return null
    return {
      id: "cred1",
      type: "public-key",
      rawId: new Uint8Array([1, 2, 3]).buffer,
      response: {
        authenticatorData: new Uint8Array([4, 5]).buffer,
        clientDataJSON: new Uint8Array([6, 7]).buffer,
        signature: new Uint8Array([8, 9]).buffer,
        userHandle: null,
      },
    } as unknown as Credential
  }
  return { fetcher, credentialsGet, isLocked: () => opts.locked ?? false }
}

describe("withWebAuthn (FR-3 / FR-4)", () => {
  test("happy path → attaches x-autostock-webauthn header to the call", async () => {
    let seen: Record<string, string> | undefined
    await withWebAuthn(fakeDeps(), async (headers) => {
      seen = headers
    })
    expect(seen).toBeDefined()
    expect(typeof seen![WEBAUTHN_HEADER]).toBe("string")
    expect(seen![WEBAUTHN_HEADER].length).toBeGreaterThan(0)
  })

  test("passkey cancelled → WebAuthnError, call NEVER runs (fail-closed)", async () => {
    let called = false
    await expect(
      withWebAuthn(fakeDeps({ cancel: true }), async () => {
        called = true
      }),
    ).rejects.toBeInstanceOf(WebAuthnError)
    expect(called).toBe(false)
  })

  test("assert-options 4xx (no passkey) → WebAuthnError, call NEVER runs", async () => {
    let called = false
    await expect(
      withWebAuthn(fakeDeps({ optionsStatus: 400 }), async () => {
        called = true
      }),
    ).rejects.toBeInstanceOf(WebAuthnError)
    expect(called).toBe(false)
  })

  test("locked → LockedError before any ceremony, call NEVER runs (NFR-6)", async () => {
    let called = false
    let fetched = false
    const deps = fakeDeps({ locked: true })
    const probed = {
      ...deps,
      fetcher: async (p: string) => {
        fetched = true
        return deps.fetcher(p)
      },
    }
    await expect(
      withWebAuthn(probed, async () => {
        called = true
      }),
    ).rejects.toBeInstanceOf(LockedError)
    expect(called).toBe(false)
    expect(fetched).toBe(false) // fail-closed before touching the authenticator
  })
})
