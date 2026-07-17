// F86 — autostock mobile dashboard read endpoint (fork-isolated; keep upstream-rebase
// surface small, mirrors server/autostock/webauthn.ts).
//
// GET /autostock/dashboard → a single read-only snapshot assembled from the daemon's
// published steering artifacts (snapshot.json / health.json / monitor.json /
// pending_approvals.json). The phone PWA polls this (~5s) and feeds it into the F79
// client cores (assembleSnapshot → toDashboard → DashboardView).
//
// Security (matches webauthn.ts):
//   - These fork routes are mounted AHEAD of the typed HttpApi, so they BYPASS the HttpApi
//     Authorization middleware. This route therefore enforces the SAME basic-auth itself
//     (checkBasicAuth) — without it the endpoint would be an unauthenticated data leak.
//   - Read-only: it never mutates state, so (unlike mutating tools) it requires no WebAuthn
//     signature — consistent with the READONLY_AUTOSTOCK_KEYS policy in webauthn.ts.
//   - Fail-safe (SECURITY-15): every file read is best-effort and the whole handler is wrapped
//     so a missing/corrupt steering file yields a partial/empty 200 payload (published_at
//     null → the client treats it as stale) rather than a 5xx that would break the shell.
//   - Read paths are FIXED filenames under the resolved steering dir — no request input is
//     ever joined into a path (no traversal).

import { readFileSync, statSync } from "node:fs"
import { join } from "node:path"
import { checkBasicAuth } from "./webauthn"

// ── response contract ────────────────────────────────────────────────────────

export type PositionRow = {
  symbol: string
  market_value: number | null
  unrealized_pnl: number | null
  return_pct: number | null // P&L % since entry (side-aware); client maps to DashboardView dayPct
  side: "long" | "short"
  current_price: number | null
}

export type DashboardPayload = {
  account: {
    equity: number | null
    cash: number | null
    day_pnl_pct: number | null // not published yet → null (F86 v1)
    buying_power: number | null // not published yet → null (F86 v1)
    open_pnl: number | null
    position_count: number
  }
  // F97 — agent vs S&P500 (SPY buy-and-hold) scorecard, derived by the daemon from the
  // equity log. null until there's a benchmark-bearing equity record.
  perf: {
    since_date: string | null
    agent_return_pct: number | null
    spy_return_pct: number | null
    alpha_pct: number | null
    agent_day_pct: number | null
    spy_day_pct: number | null
    day_alpha_pct: number | null
  } | null
  positions: PositionRow[]
  health: { status?: string; ok?: boolean; summary?: string } | null
  pending_approvals: number
  market: { open: boolean | null; phase?: string; label?: string } | null
  agent: {
    current: string | null
    // `ts` is the daemon's pre-formatted clock string ("HH:MM"), for DISPLAY only — it is NOT
    // an ISO timestamp (unlike `published_at`). Do not Date.parse() it.
    recent: Array<{ ts?: string; action: string; symbol?: string; summary?: string }>
  }
  published_at: string | null
}

export const EMPTY_PAYLOAD: DashboardPayload = {
  account: { equity: null, cash: null, day_pnl_pct: null, buying_power: null, open_pnl: null, position_count: 0 },
  perf: null,
  positions: [],
  health: null,
  pending_approvals: 0,
  market: null,
  agent: { current: null, recent: [] },
  published_at: null,
}

// ── pure helpers ───────────────────────────────────────────────────────────--

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}
function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined
}

/**
 * Resolve the daemon's steering directory the same way the rest of the console does:
 *   STEERING_DIR (explicit) → AUTOSTOCK_ROOT/steering → <cwd>/../../steering (console cwd =
 *   operator-console/cli, so ../../ is the repo root). Returns the first that exists as a
 *   directory, else null. Never throws.
 */
export function resolveSteeringDir(
  env: Record<string, string | undefined> = process.env,
  cwd: string = process.cwd(),
): string | null {
  const candidates: string[] = []
  if (env.STEERING_DIR) candidates.push(env.STEERING_DIR)
  if (env.AUTOSTOCK_ROOT) candidates.push(join(env.AUTOSTOCK_ROOT, "steering"))
  candidates.push(join(cwd, "..", "..", "steering"))
  for (const dir of candidates) {
    try {
      if (statSync(dir).isDirectory()) return dir
    } catch {
      // missing/inaccessible → try next
    }
  }
  return null
}

export type RawSteering = {
  snapshot?: unknown
  health?: unknown
  monitor?: unknown
  pending?: unknown
  snapshotMtimeIso?: string | null
}

// F97 — the daemon publishes snapshot.perf_vs_benchmark (see src/agent/logs/performance.py).
// Defensive: any missing/malformed piece degrades to null, never throws.
function toPerf(v: unknown): DashboardPayload["perf"] {
  if (!isObj(v)) return null
  return {
    since_date: str(v.since_date) ?? null,
    agent_return_pct: num(v.agent_return_pct),
    spy_return_pct: num(v.spy_return_pct),
    alpha_pct: num(v.alpha_pct),
    agent_day_pct: num(v.agent_day_pct),
    spy_day_pct: num(v.spy_day_pct),
    day_alpha_pct: num(v.day_alpha_pct),
  }
}

function toPositionRow(symbol: string, p: unknown): PositionRow {
  const o = isObj(p) ? p : {}
  const side = o.side === "short" ? "short" : "long"
  const avg = num(o.avg_entry_price)
  const cur = num(o.current_price)
  let return_pct: number | null = null
  if (avg !== null && avg !== 0 && cur !== null) {
    const raw = ((cur - avg) / avg) * 100
    return_pct = side === "short" ? -raw : raw
  }
  return {
    symbol,
    market_value: num(o.market_value),
    unrealized_pnl: num(o.unrealized_pnl),
    return_pct,
    side,
    current_price: cur,
  }
}

/**
 * Shape the read steering artifacts into the dashboard payload. NEVER THROWS: any missing or
 * malformed piece degrades to null/empty so the client renders a partial-but-honest model
 * (SECURITY-15 / NFR-3). day_pnl_pct and buying_power are not published by the daemon yet, so
 * they are always null in v1 (no fabricated values).
 */
export function assembleDashboardPayload(raw: RawSteering): DashboardPayload {
  const snapshot = isObj(raw.snapshot) ? raw.snapshot : {}
  const account = isObj(snapshot.account) ? snapshot.account : {}
  const monitor = isObj(raw.monitor) ? raw.monitor : {}

  // positions: dict → array (preserve every symbol)
  const posDict = isObj(snapshot.positions) ? snapshot.positions : {}
  const positions = Object.keys(posDict).map((sym) => toPositionRow(sym, posDict[sym]))

  // health: the daemon's health.json reports `overall` ("OK"/"WARN"/"ERROR"), not status/ok —
  // so map it to the {status, ok} shape the F79 dashboard core expects (and trim the large
  // per-dimension blob to a compact summary; the phone only needs the at-a-glance state).
  let health: DashboardPayload["health"] = null
  if (isObj(raw.health)) {
    const h = raw.health
    const overall = str(h.overall) ?? str(h.status)
    health = {
      status: overall ? overall.toLowerCase() : undefined,
      ok: overall ? overall.toUpperCase() === "OK" : h.ok === true ? true : undefined,
      summary: str(h.summary),
    }
  }

  // pending count: pending_approvals.json (array) → snapshot.pending length → 0.
  // Always a non-negative integer (a stray fractional/negative number is sanitized).
  let pending = 0
  if (Array.isArray(raw.pending)) pending = raw.pending.length
  else if (typeof raw.pending === "number" && Number.isFinite(raw.pending)) pending = Math.max(0, Math.trunc(raw.pending))
  else if (Array.isArray(snapshot.pending)) pending = (snapshot.pending as unknown[]).length

  // market: monitor.market (rich) → snapshot.market_open (bool)
  let market: DashboardPayload["market"] = null
  const mRule = monitor.market
  const openBool = typeof snapshot.market_open === "boolean" ? snapshot.market_open : null
  if (isObj(mRule)) {
    market = { open: openBool, phase: str(mRule.phase), label: str(mRule.label) ?? str(mRule.name) }
  } else if (openBool !== null) {
    market = { open: openBool }
  }

  // agent: current_turn + decisions tail
  const ct = monitor.current_turn
  let current: string | null = null
  if (isObj(ct)) current = str(ct.type) ?? str(ct.label) ?? str(ct.summary) ?? null
  else if (typeof ct === "string") current = ct
  const decisions = Array.isArray(monitor.decisions) ? monitor.decisions : []
  const recent = decisions
    .filter(isObj)
    .map((d) => ({
      ts: str(d.ts),
      action: str(d.action) ?? str(d.verb) ?? "decision",
      symbol: str(d.symbol),
      summary: str(d.summary) ?? str(d.detail),
    }))

  // published_at = the SNAPSHOT's own freshness, NOT monitor's. account/positions/market_open
  // all come from snapshot.json, which the daemon stamps with `published_at` ONLY when it
  // actually writes it (channel.publish_snapshot). If publish_snapshot fails (broker error) it
  // returns without writing, so this stamp freezes — the correct stale signal. monitor.json's
  // `ts` ticks on an independent timer and must NOT vouch for snapshot freshness (it would mask
  // a frozen snapshot as fresh — NFR-2/SECURITY-15). Fall back to the snapshot file mtime.
  const published_at =
    str(snapshot.published_at) ?? (typeof raw.snapshotMtimeIso === "string" ? raw.snapshotMtimeIso : null)

  return {
    account: {
      equity: num(account.equity),
      cash: num(account.cash),
      day_pnl_pct: null,
      buying_power: null,
      open_pnl: num(account.open_pnl),
      // Single source of truth = the positions we actually return (matches the F79 core,
      // which derives positionCount from the positions list — never let the two disagree).
      position_count: positions.length,
    },
    perf: toPerf(snapshot.perf_vs_benchmark),
    positions,
    health,
    pending_approvals: pending,
    market,
    agent: { current, recent },
    published_at,
  }
}

// ── route ────────────────────────────────────────────────────────────────────

function readJson(dir: string, file: string): unknown | undefined {
  try {
    return JSON.parse(readFileSync(join(dir, file), "utf8"))
  } catch {
    return undefined
  }
}
function mtimeIso(dir: string, file: string): string | null {
  try {
    return statSync(join(dir, file)).mtime.toISOString()
  } catch {
    return null
  }
}
function unauthorized(): Response {
  return new Response("Unauthorized", { status: 401, headers: { "WWW-Authenticate": "Basic" } })
}

let warnedCwdFallback = false

export async function route(request: Request): Promise<Response | null> {
  const url = new URL(request.url)
  if (url.pathname !== "/autostock/dashboard") return null
  if (request.method !== "GET") return new Response("Method Not Allowed", { status: 405 })
  // Same basic-auth as every other endpoint — these fork routes bypass the HttpApi auth
  // middleware, so without this the dashboard data would be unauthenticated (SECURITY-08).
  if (!checkBasicAuth(request.headers.get("authorization"))) return unauthorized()

  try {
    const dir = resolveSteeringDir()
    // Neither STEERING_DIR nor AUTOSTOCK_ROOT set → we fell back to a cwd-relative guess, which
    // is only correct when the server's cwd is operator-console/cli. Warn once so an operator
    // can spot a wrong/empty dashboard caused by a non-standard launch cwd (see post-merge-guide).
    if (!warnedCwdFallback && !process.env.STEERING_DIR && !process.env.AUTOSTOCK_ROOT) {
      warnedCwdFallback = true
      console.warn(
        `[autostock] dashboard: STEERING_DIR/AUTOSTOCK_ROOT unset; using cwd-relative steering dir guess (${dir ?? "none found"}). Set STEERING_DIR to be explicit.`,
      )
    }
    const raw: RawSteering = dir
      ? {
          snapshot: readJson(dir, "snapshot.json"),
          health: readJson(dir, "health.json"),
          monitor: readJson(dir, "monitor.json"),
          pending: readJson(dir, "pending_approvals.json"),
          snapshotMtimeIso: mtimeIso(dir, "snapshot.json"),
        }
      : {}
    return Response.json(assembleDashboardPayload(raw))
  } catch {
    // Fail-safe: never 5xx the shell over a read/parse error (SECURITY-15 / NFR-3).
    return Response.json(EMPTY_PAYLOAD)
  }
}
