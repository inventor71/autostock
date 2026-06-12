// F71 U2 — autostock mobile security gate (fork-isolated; keep upstream-rebase surface small).
//
// What this enforces (US-5, Security Baseline; F75 hardening):
//   A *remote* approval of a MUTATING autostock permission requires a fresh WebAuthn
//   (passkey) assertion, verified SERVER-SIDE. "Remote" is decided by origin classification
//   (see isRemoteOrigin): non-loopback sockets, and loopback sockets carrying a Tailscale
//   identity header (the tailscale-serve proxy hop — so a phone proxied to loopback is still
//   gated). In-process calls (embedded TUI) and plain host-local loopback (attach-mode TUI)
//   are trusted: the host is the trust boundary. A phone client (PWA over the tailnet) must
//   attach the assertion in the `x-autostock-webauthn` header of the permission-reply request.
//
// Mutating classification is FAIL-CLOSED: any `autostock_*` permission key that is not in the
// known read-only set counts as mutating — a future tool added without updating this file
// demands a signature rather than silently skipping the gate. (Read-only keys never reach
// "ask" anyway under opencode.json, so this only matters for misconfiguration.)
//
// WebAuthn requires a secure context on the client. Over Tailscale that means fronting the
// server with `tailscale serve` (TLS on the *.ts.net hostname). The expected origin/rpID come
// from AUTOSTOCK_WEBAUTHN_ORIGIN (e.g. https://pc.tailnet.ts.net); verification fails closed
// when it is unset.

import { createHash, timingSafeEqual } from "node:crypto"
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { Global } from "@opencode-ai/core/global"

// ── mutating classification (pure) ──────────────────────────────────────────

const READONLY_AUTOSTOCK_KEYS = new Set([
  "autostock_steer_read",
  "autostock_get_account_info",
  "autostock_get_all_positions",
  "autostock_get_open_position",
  "autostock_get_portfolio_history",
  "autostock_get_asset",
  "autostock_get_all_assets",
  "autostock_get_calendar",
  "autostock_get_market_clock",
  "autostock_get_stock_bars",
  "autostock_get_stock_latest_bar",
  "autostock_get_stock_latest_quote",
  "autostock_get_stock_latest_trade",
  "autostock_get_stock_quote",
  "autostock_get_stock_snapshot",
  "autostock_get_stock_trades",
  "autostock_get_orders",
])

export function isMutatingAutostockPermission(permission: string): boolean {
  if (!permission.startsWith("autostock_")) return false
  return !READONLY_AUTOSTOCK_KEYS.has(permission)
}

// ── request-origin classification (pure) ─────────────────────────────────────
//
// Trust boundary = the HOST. Three origins, decided from the socket address plus the
// Tailscale identity header that `tailscale serve` injects at the proxy hop:
//   in-process — no socket (embedded TUI via app.fetch)                    → trusted
//   host-local — loopback socket WITHOUT a Tailscale identity header        → trusted
//                (attach-mode TUI and anything else already on the host; a process
//                 that can open a loopback socket owns the box anyway)
//   remote     — non-loopback socket, OR loopback WITH a Tailscale identity header
//                (= the tailscale-serve proxy dialing in from the tailnet; the proxy
//                 overwrites client-sent Tailscale-* headers, so a phone cannot strip
//                 it to masquerade as host-local)                           → gated

export function isLoopbackAddress(addr: string | undefined): boolean {
  if (!addr) return false // no socket is classified separately (in-process)
  const a = addr.replace(/^::ffff:/, "")
  return a === "127.0.0.1" || a === "::1" || a.startsWith("127.")
}

export function isRemoteOrigin(remoteAddress: string | undefined, tailscaleIdentity: boolean): boolean {
  if (remoteAddress === undefined) return false // in-process (embedded TUI)
  if (!isLoopbackAddress(remoteAddress)) return true
  return tailscaleIdentity // loopback: only the tailscale-serve proxy hop is remote
}

// ── gate decision (pure core — unit-tested without crypto/Effect) ───────────

export type GateInput = {
  reply: "once" | "always" | "reject"
  remoteAddress: string | undefined
  /** true when the request carries a Tailscale identity header (tailscale-serve hop). */
  tailscaleIdentity: boolean
  permission: string | undefined // undefined = pending request not found (let reply 404 itself)
  assertionValid: boolean
}

/** null = allow through; string = deny with this reason. */
export function decideGate(input: GateInput): string | null {
  if (input.reply === "reject") return null // rejecting is always safe
  if (!isRemoteOrigin(input.remoteAddress, input.tailscaleIdentity)) return null
  if (input.permission === undefined) return null
  if (!isMutatingAutostockPermission(input.permission)) return null
  if (input.assertionValid) return null
  return (
    `autostock: '${input.permission}' 원격 승인은 WebAuthn 패스키 서명이 필요합니다 ` +
    `(x-autostock-webauthn 헤더 누락/무효). 폰에서 지문 확인 후 다시 시도하세요.`
  )
}

// ── passkey store (public keys only — never secrets) ────────────────────────

export type StoredCredential = {
  id: string // base64url credential id
  publicKey: string // base64url COSE public key
  counter: number
  transports?: string[]
}

type Store = { credentials: StoredCredential[] }

export function storePath(): string {
  return join(Global.Path.data, "autostock-passkeys.json")
}

export function loadStore(path = storePath()): Store {
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8"))
    if (Array.isArray(parsed?.credentials)) return { credentials: parsed.credentials }
  } catch {}
  return { credentials: [] }
}

export function saveStore(store: Store, path = storePath()): void {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, JSON.stringify(store, null, 2), "utf8")
}

// ── challenge store (in-memory, single-use, TTL, value-keyed) ────────────────
//
// Keyed by the challenge VALUE (not a global per-kind slot) so two approvals in
// flight don't invalidate each other's challenge. The client tells us which
// challenge it signed via clientDataJSON; we consume exactly that one.

export const CHALLENGE_TTL_MS = 2 * 60 * 1000
export const CHALLENGE_MAX = 256 // cap: a basic-auth holder spamming *-options can't grow memory unboundedly

type Challenge = { kind: "register" | "assert"; expires: number }
const challenges = new Map<string, Challenge>()

export function issueChallenge(kind: "register" | "assert", now = Date.now(), value?: string): string {
  for (const [v, c] of challenges) if (c.expires < now) challenges.delete(v) // sweep expired
  while (challenges.size >= CHALLENGE_MAX) {
    // evict oldest (Map preserves insertion order) — flooding only invalidates the
    // flooder's own pending ceremonies, never grows memory
    const oldest = challenges.keys().next().value
    if (oldest === undefined) break
    challenges.delete(oldest)
  }
  const v = value ?? crypto.randomUUID().replaceAll("-", "")
  challenges.set(v, { kind, expires: now + CHALLENGE_TTL_MS })
  return v
}

/** Single-use: consuming removes it. Returns false when absent/expired/wrong-kind. */
export function consumeChallenge(kind: "register" | "assert", value: string | null, now = Date.now()): boolean {
  if (!value) return false
  const c = challenges.get(value)
  challenges.delete(value)
  return !!c && c.kind === kind && c.expires >= now
}

/** The base64url challenge the client actually signed, from clientDataJSON. */
export function extractClientChallenge(response: unknown): string | null {
  try {
    const cdj = (response as { response?: { clientDataJSON?: string } })?.response?.clientDataJSON
    if (!cdj) return null
    const parsed = JSON.parse(Buffer.from(cdj, "base64url").toString("utf8"))
    return typeof parsed?.challenge === "string" ? parsed.challenge : null
  } catch {
    return null
  }
}

// ── expected origin / rpID (env-driven; fail-closed) ────────────────────────

export function expectedOrigin(env: Record<string, string | undefined> = process.env): string | null {
  const o = env.AUTOSTOCK_WEBAUTHN_ORIGIN?.trim()
  if (!o) return null
  try {
    const u = new URL(o)
    return u.protocol === "https:" ? u.origin : null // WebAuthn needs a secure context
  } catch {
    return null
  }
}

export function expectedRpId(env: Record<string, string | undefined> = process.env): string | null {
  const o = expectedOrigin(env)
  if (!o) return null
  return new URL(o).hostname
}

// ── assertion verification (thin wrapper; injectable for tests) ─────────────

export type VerifyResult = { ok: boolean; reason?: string }

export async function verifyAssertionHeader(
  header: string | undefined,
  deps: {
    env?: Record<string, string | undefined>
    load?: typeof loadStore
    save?: typeof saveStore
    consume?: typeof consumeChallenge
  } = {},
): Promise<VerifyResult> {
  const env = deps.env ?? process.env
  const load = deps.load ?? loadStore
  const save = deps.save ?? saveStore
  const consume = deps.consume ?? consumeChallenge

  if (!header) return { ok: false, reason: "missing header" }
  const origin = expectedOrigin(env)
  const rpID = expectedRpId(env)
  if (!origin || !rpID) return { ok: false, reason: "AUTOSTOCK_WEBAUTHN_ORIGIN unset (https origin required)" }

  let response: unknown
  try {
    response = JSON.parse(Buffer.from(header, "base64").toString("utf8"))
  } catch {
    return { ok: false, reason: "header is not base64 JSON" }
  }

  const challenge = extractClientChallenge(response)
  if (!challenge || !consume("assert", challenge))
    return { ok: false, reason: "no fresh challenge (request /autostock/webauthn/assert-options first)" }

  const store = load()
  const credId = (response as { id?: string })?.id
  const cred = store.credentials.find((c) => c.id === credId)
  if (!cred) return { ok: false, reason: "unknown credential" }

  try {
    const { verifyAuthenticationResponse } = await import("@simplewebauthn/server")
    const verification = await verifyAuthenticationResponse({
      response: response as Parameters<typeof verifyAuthenticationResponse>[0]["response"],
      expectedChallenge: challenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
      credential: {
        id: cred.id,
        publicKey: Buffer.from(cred.publicKey, "base64url"),
        counter: cred.counter,
        transports: cred.transports as never,
      },
    })
    if (!verification.verified) return { ok: false, reason: "assertion not verified" }
    cred.counter = verification.authenticationInfo.newCounter
    save(store)
    return { ok: true }
  } catch (e) {
    return { ok: false, reason: `verify error: ${(e as Error).message}` }
  }
}

/** One-call gate for the permission-reply handlers: null = proceed, string = deny reason.
 *  Pure decision first (cheap), crypto verification only when actually required. */
export async function checkReply(input: {
  reply: "once" | "always" | "reject"
  remoteAddress: string | undefined
  /** value of the `tailscale-user-login` request header, if any (proxy hop marker). */
  tailscaleUserLogin: string | undefined
  permission: string | undefined
  header: string | undefined
}): Promise<string | null> {
  const wouldDeny = decideGate({
    reply: input.reply,
    remoteAddress: input.remoteAddress,
    tailscaleIdentity: input.tailscaleUserLogin !== undefined,
    permission: input.permission,
    assertionValid: false,
  })
  if (wouldDeny === null) return null
  const v = await verifyAssertionHeader(input.header)
  return v.ok ? null : `${wouldDeny} [${v.reason}]`
}

// ── HTTP routes (mounted ahead of the HttpApi app in server.ts) ──────────────
//
// POST /autostock/webauthn/register-options  → registration options (challenge, rp, user)
// POST /autostock/webauthn/register          → store the new passkey credential
// POST /autostock/webauthn/assert-options    → authentication options for a signature
//
// All three require the server basic-auth password (same as every other endpoint).

function unauthorized(): Response {
  return new Response("Unauthorized", { status: 401, headers: { "WWW-Authenticate": "Basic" } })
}

export function checkBasicAuth(
  authHeader: string | null,
  env: Record<string, string | undefined> = process.env,
): boolean {
  const password = env.OPENCODE_SERVER_PASSWORD ?? ""
  if (!password) return false // no password configured → refuse (serve fail-closes earlier anyway)
  if (!authHeader?.startsWith("Basic ")) return false
  try {
    const decoded = Buffer.from(authHeader.slice(6), "base64").toString("utf8")
    const idx = decoded.indexOf(":")
    if (idx < 0) return false
    // Constant-time compare (hash both sides so length differences don't leak either).
    const a = createHash("sha256").update(decoded.slice(idx + 1)).digest()
    const b = createHash("sha256").update(password).digest()
    return timingSafeEqual(a, b)
  } catch {
    return false
  }
}

export async function route(request: Request): Promise<Response | null> {
  const url = new URL(request.url)
  if (!url.pathname.startsWith("/autostock/webauthn/")) return null
  if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 })
  if (!checkBasicAuth(request.headers.get("authorization"))) return unauthorized()

  const origin = expectedOrigin()
  const rpID = expectedRpId()
  if (!origin || !rpID) {
    return Response.json(
      { error: "AUTOSTOCK_WEBAUTHN_ORIGIN 미설정 — https origin(예: tailscale serve의 *.ts.net)을 설정하세요." },
      { status: 503 },
    )
  }

  const action = url.pathname.slice("/autostock/webauthn/".length)

  if (action === "register-options") {
    const { generateRegistrationOptions } = await import("@simplewebauthn/server")
    const store = loadStore()
    const options = await generateRegistrationOptions({
      rpName: "autostock",
      rpID,
      userName: "operator",
      attestationType: "none",
      excludeCredentials: store.credentials.map((c) => ({ id: c.id })),
      authenticatorSelection: { residentKey: "preferred", userVerification: "required" },
    })
    issueChallenge("register", Date.now(), options.challenge)
    return Response.json(options)
  }

  if (action === "register") {
    // Enrollment lock: once a passkey exists, adding another requires a fresh assertion
    // from an EXISTING passkey (x-autostock-webauthn) — the server password alone must
    // not be able to mint new signing credentials.
    //
    // Bootstrap (no passkey yet): the FIRST enrollment must not come through the
    // tailscale-serve proxy hop (identity header present) — otherwise a phished server
    // password alone could mint the first signing credential remotely. route() has no
    // socket info (plain Request), so this covers the proxied path; enroll the first key
    // from the host (see post-merge-guide).
    {
      const store = loadStore()
      if (store.credentials.length === 0 && request.headers.get("tailscale-user-login") !== null) {
        return Response.json(
          { error: "첫 패스키 등록은 원격(tailscale 프록시)에서 불가 — 호스트에서 등록하세요." },
          { status: 403 },
        )
      }
      if (store.credentials.length > 0) {
        const v = await verifyAssertionHeader(request.headers.get("x-autostock-webauthn") ?? undefined)
        if (!v.ok) {
          return Response.json(
            { error: `패스키가 이미 등록돼 있어 추가 등록에는 기존 패스키 서명이 필요합니다 [${v.reason}]` },
            { status: 403 },
          )
        }
      }
    }
    const body = await request.json().catch(() => null)
    if (!body) return Response.json({ error: "invalid body" }, { status: 400 })
    const challenge = extractClientChallenge(body)
    if (!challenge || !consumeChallenge("register", challenge))
      return Response.json({ error: "no fresh challenge" }, { status: 400 })
    try {
      const { verifyRegistrationResponse } = await import("@simplewebauthn/server")
      const verification = await verifyRegistrationResponse({
        response: body,
        expectedChallenge: challenge,
        expectedOrigin: origin,
        expectedRPID: rpID,
        requireUserVerification: true,
      })
      if (!verification.verified || !verification.registrationInfo) {
        return Response.json({ error: "registration not verified" }, { status: 400 })
      }
      const info = verification.registrationInfo
      const store = loadStore()
      store.credentials.push({
        id: info.credential.id,
        publicKey: Buffer.from(info.credential.publicKey).toString("base64url"),
        counter: info.credential.counter,
        transports: info.credential.transports,
      })
      saveStore(store)
      return Response.json({ ok: true })
    } catch (e) {
      return Response.json({ error: (e as Error).message }, { status: 400 })
    }
  }

  if (action === "assert-options") {
    const { generateAuthenticationOptions } = await import("@simplewebauthn/server")
    const store = loadStore()
    if (store.credentials.length === 0) {
      return Response.json({ error: "등록된 패스키가 없습니다 — 먼저 register 하세요." }, { status: 400 })
    }
    const options = await generateAuthenticationOptions({
      rpID,
      userVerification: "required",
      allowCredentials: store.credentials.map((c) => ({ id: c.id })),
    })
    issueChallenge("assert", Date.now(), options.challenge)
    return Response.json(options)
  }

  return new Response("Not Found", { status: 404 })
}
