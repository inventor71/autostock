// F93 — listener-through regression for the autostock fork routes.
//
// The bug: webauthn.route() + dashboard-read.route() were mounted ONLY on Server.Default().app.fetch,
// but Server.listen() serves via createRoutes() and never invokes that fetch chain — so over the wire
// every /autostock/* request fell through to the uiRoute `/*` catch-all and returned the SPA HTML.
// F71/F86 unit tests passed because they call route() directly; nothing exercised the real listener.
//
// These tests start an actual Server.listen() and fetch over the socket, asserting the autostock API
// routes return JSON (NOT text/html) — the assertion that would have caught the regression. SPA
// fallback for the /autostock shell page (uiRoute) proxies upstream and is covered by the live smoke
// (mobile-realdevice-test-guide §9), not here, to keep this test network-free.
import { afterEach, describe, expect, test } from "bun:test"
import { Flag } from "@opencode-ai/core/flag/flag"
import * as Log from "@opencode-ai/core/util/log"
import { Server } from "../../src/server/server"
import { withTimeout } from "../../src/util/timeout"
import { resetDatabase } from "../fixture/db"
import { disposeAllInstances } from "../fixture/fixture"

void Log.init({ print: false })

const auth = { username: "opencode", password: "f93-listener-secret" }
const TEST_ORIGIN = "https://test.example.ts.net"

const original = {
  password: process.env.OPENCODE_SERVER_PASSWORD,
  username: process.env.OPENCODE_SERVER_USERNAME,
  origin: process.env.AUTOSTOCK_WEBAUTHN_ORIGIN,
  flagPassword: Flag.OPENCODE_SERVER_PASSWORD,
  flagUsername: Flag.OPENCODE_SERVER_USERNAME,
}

afterEach(async () => {
  Flag.OPENCODE_SERVER_PASSWORD = original.flagPassword
  Flag.OPENCODE_SERVER_USERNAME = original.flagUsername
  const restore = (k: string, v: string | undefined) => (v === undefined ? delete process.env[k] : (process.env[k] = v))
  restore("OPENCODE_SERVER_PASSWORD", original.password)
  restore("OPENCODE_SERVER_USERNAME", original.username)
  restore("AUTOSTOCK_WEBAUTHN_ORIGIN", original.origin)
  await disposeAllInstances()
  await resetDatabase()
})

async function startListener() {
  Flag.OPENCODE_SERVER_PASSWORD = auth.password
  Flag.OPENCODE_SERVER_USERNAME = auth.username
  process.env.OPENCODE_SERVER_PASSWORD = auth.password
  process.env.OPENCODE_SERVER_USERNAME = auth.username
  process.env.AUTOSTOCK_WEBAUTHN_ORIGIN = TEST_ORIGIN
  return Server.listen({ hostname: "127.0.0.1", port: 0 })
}

function authorization() {
  return `Basic ${btoa(`${auth.username}:${auth.password}`)}`
}

function stop(listener: Awaited<ReturnType<typeof startListener>>) {
  return withTimeout(listener.stop(true), 10_000, "timed out stopping listener")
}

describe("F93 — autostock routes on Server.listen()", () => {
  test("GET /autostock/dashboard reaches the F86 route (JSON, not the SPA catch-all)", async () => {
    const listener = await startListener()
    try {
      const res = await fetch(new URL("/autostock/dashboard", listener.url), {
        headers: { authorization: authorization() },
      })
      // Before the fix: 200 text/html (SPA index). After: 200 application/json with the payload shape.
      expect(res.status).toBe(200)
      expect(res.headers.get("content-type") ?? "").toContain("json")
      const body = (await res.json()) as Record<string, unknown>
      // assembleDashboardPayload always emits these keys (empty/null when the daemon isn't publishing).
      expect(body).toHaveProperty("published_at")
      expect(body).toHaveProperty("account")
    } finally {
      await stop(listener)
    }
  })

  test("GET /autostock/dashboard without auth → 401 (not the SPA page)", async () => {
    const listener = await startListener()
    try {
      const res = await fetch(new URL("/autostock/dashboard", listener.url))
      expect(res.status).toBe(401)
    } finally {
      await stop(listener)
    }
  })

  test("POST /autostock/dashboard → 405 (read-only route, reached not shadowed)", async () => {
    const listener = await startListener()
    try {
      const res = await fetch(new URL("/autostock/dashboard", listener.url), {
        method: "POST",
        headers: { authorization: authorization() },
      })
      expect(res.status).toBe(405)
    } finally {
      await stop(listener)
    }
  })

  test("POST /autostock/webauthn/register-options reaches the F71 route (JSON challenge, not SPA)", async () => {
    const listener = await startListener()
    try {
      const res = await fetch(new URL("/autostock/webauthn/register-options", listener.url), {
        method: "POST",
        headers: { authorization: authorization(), "content-type": "application/json" },
        body: "{}",
      })
      // The regression guard: a JSON body proves the webauthn route handled it (the SPA catch-all
      // would return text/html). With AUTOSTOCK_WEBAUTHN_ORIGIN set this is a 200 challenge.
      expect(res.headers.get("content-type") ?? "").toContain("json")
      expect(res.status).toBe(200)
      const body = (await res.json()) as Record<string, unknown>
      expect(body).toHaveProperty("challenge")
    } finally {
      await stop(listener)
    }
  })

  test("GET /autostock/webauthn/register-options → 405 (route requires POST)", async () => {
    const listener = await startListener()
    try {
      const res = await fetch(new URL("/autostock/webauthn/register-options", listener.url), {
        headers: { authorization: authorization() },
      })
      expect(res.status).toBe(405)
    } finally {
      await stop(listener)
    }
  })

  test("/doc still served — typed routes unaffected by the autostock mount", async () => {
    const listener = await startListener()
    try {
      const res = await fetch(new URL("/doc", listener.url), { headers: { authorization: authorization() } })
      expect(res.status).toBe(200)
    } finally {
      await stop(listener)
    }
  })
})
