import { readFileSync, existsSync } from "fs"
import { join } from "path"
import type { MonitorData, MonitorTurn, MonitorDecision, InterventionMarker, AgentReport } from "../types"

// F25 FR-2: resolve a session's turns + interventions for a given ET date.
// The current/upcoming session comes straight from monitor.json (live). For any
// other date the TUI reads turns.jsonl / human_directives.jsonl directly and
// filters by et_date — giving unlimited history (Q4=C) with no request channel.

export interface SessionData {
  turns: MonitorTurn[]
  interventions: InterventionMarker[]
  decisions: MonitorDecision[]
}

/**
 * turn_id whose started_at is the most recent at or before a decision's ts.
 * Mirrors `_correlate_turn` in src/agent/steering/runtime.py (decisions.jsonl has no
 * turn_id for older records, so the daemon assigns one the same way). `turnIdx` is the
 * date's turns as [started_at|ts, id] in file (chronological append) order; reversed-first
 * match = the latest turn that had started. Compares by instant when both timestamps parse,
 * else falls back to the lexical compare the Python uses.
 */
export function correlateTurnId(ts: string, turnIdx: Array<[string, string]>): string | null {
  if (!ts || turnIdx.length === 0) return null
  const dms = Date.parse(ts)
  for (let i = turnIdx.length - 1; i >= 0; i--) {
    const [started, tid] = turnIdx[i]!
    if (!started) continue
    const sms = Date.parse(started)
    const leq = !Number.isNaN(sms) && !Number.isNaN(dms) ? sms <= dms : started <= ts
    if (leq) return tid
  }
  return null
}

function normalizeAction(v: unknown): MonitorDecision["action"] {
  const a = String(v ?? "").toUpperCase()
  return a === "BUY" || a === "SELL" || a === "HOLD" || a === "ADJUST_STOP" ? a : "HOLD"
}

const TRADE_VERBS = new Set([
  "buy", "sell", "short", "cover", "flatten", "flatten_all", "place_order",
  "cancel", "cancel_order", "cancel_all", "close_position", "close_all",
])

function readJsonl(path: string): any[] {
  if (!existsSync(path)) return []
  let text: string
  try {
    text = readFileSync(path, "utf-8")
  } catch {
    return []
  }
  const out: any[] = []
  for (const line of text.split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(JSON.parse(t))
    } catch {
      // torn trailing line / corruption — skip
    }
  }
  return out
}

/** ET trading date for a record: prefer the stored et_date, else derive from ts. */
function recordEtDate(rec: { et_date?: string; ts?: string }): string {
  if (rec.et_date) return rec.et_date
  if (!rec.ts) return ""
  const ms = Date.parse(rec.ts)
  if (Number.isNaN(ms)) return ""
  // Convert to America/New_York calendar date.
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date(ms))
  return parts // en-CA yields YYYY-MM-DD
}

function symbolFromArgs(args: any): string | null {
  const s = args?.symbol
  return s ? String(s).toUpperCase() : null
}

export function readSessionData(
  monitor: MonitorData | null,
  etDate: string,
): SessionData {
  if (!monitor) return { turns: [], interventions: [], decisions: [] }

  // Live session: use the already-filtered monitor payload (decisions already carry turn_id).
  if (etDate === monitor.session_et_date) {
    return {
      turns: monitor.turns?.recent ?? [],
      interventions: monitor.interventions ?? [],
      decisions: monitor.decisions ?? [],
    }
  }

  // Historical: read the date's journal files. Keyed only by (workspace_root, etDate),
  // so the timeline can depend on those alone and NOT re-read on every live-monitor poll.
  return readHistoricalSession(monitor.workspace_root ?? null, etDate)
}

/**
 * Read one ET date's session straight from the journal files (turns / decisions /
 * human_directives), filtered by ET date. A pure function of (root, etDate) — no live
 * monitor — so callers can memoize on those keys and avoid re-reading (and re-rendering
 * every marker) on each ~1.5s monitor poll.
 */
export function readHistoricalSession(root: string | null, etDate: string): SessionData {
  if (!root) return { turns: [], interventions: [], decisions: [] }

  const rawTurns = readJsonl(join(root, "turns.jsonl"))
    .filter((r) => recordEtDate(r) === etDate)

  const turns: MonitorTurn[] = rawTurns.map((r) => ({
    id: r.turn_id ?? r.id ?? "",
    type: r.turn_type ?? r.type ?? "intraday",
    ts: r.ts ?? "",
    et_date: r.et_date,
    cost_usd: Number(r.cost_usd ?? 0),
    num_decisions: Number(r.num_decisions ?? 0),
    duration_ms: r.duration_ms ?? null,
    summary: r.summary ?? "",
    health: r.health === "error" ? "error" : "ok",
  }))

  // Turn index for decision→turn correlation (decisions.jsonl carries no turn_id/et_date).
  const turnIdx: Array<[string, string]> = rawTurns.map((r) => [
    String(r.started_at ?? r.ts ?? ""),
    String(r.turn_id ?? r.id ?? ""),
  ])

  // decisions.jsonl rows have no et_date and (for daemon-written rows) a NAIVE ts. recordEtDate
  // and correlateTurnId interpret a naive ts in the host's local tz → ET — the same convention as
  // the Python writer (`compute_et_date` in src/agent/turn_log.py), so this stays consistent as
  // long as the console runs on the same clock as the daemon (it does: same host/container). A
  // remote console in a different tz would mis-bucket naive-ts decisions — a project-wide caveat,
  // not specific to this path.
  const decisions: MonitorDecision[] = readJsonl(join(root, "decisions.jsonl"))
    .filter((r) => recordEtDate(r) === etDate)
    .map((r) => ({
      turn_id: r.turn_id ?? correlateTurnId(String(r.ts ?? ""), turnIdx),
      ts: r.ts ?? "",
      symbol: String(r.symbol ?? "?"),
      action: normalizeAction(r.action),
      confidence: r.confidence != null ? Number(r.confidence) : null,
      reason: String(r.reason ?? ""),
      source: r.source === "human" ? "human" : "agent",
    }))

  const interventions: InterventionMarker[] = readJsonl(join(root, "human_directives.jsonl"))
    .filter((r) => TRADE_VERBS.has(String(r.command ?? "")))
    .filter((r) => recordEtDate(r) === etDate)
    .map((r) => ({
      ts: r.ts ?? "",
      et_date: recordEtDate(r),
      verb: String(r.command ?? ""),
      symbol: symbolFromArgs(r.args),
      outcome: r.outcome ?? "",
      detail: r.detail ?? "",
    }))

  return { turns, interventions, decisions }
}

// F41: redact obvious secrets from agent evaluation text before display, mirroring
// `_mask_secrets` in src/agent/steering/runtime.py (the value after a token/key/secret
// key, and any long opaque hex/base64 run). The evaluations are the agent's own
// reasoning — same trust class as the decision `reason` shown elsewhere — but masking
// here keeps the exposure posture explicit (NFR-4).
const SECRET_KV = /\b(token|secret|api[_-]?key|password|authorization)\b(\s*[=:]\s*)\S+/gi
const SECRET_BLOB = /\b[A-Za-z0-9_-]{24,}\b/g

export function maskSecrets(text: string): string {
  if (!text) return ""
  return text.replace(SECRET_KV, (_m, k, sep) => `${k}${sep}***`).replace(SECRET_BLOB, "***")
}

/**
 * F41: read a turn's persisted multi-agent evaluation report
 * (workspace/agent_reports/<turn_id>.json), or null if the turn was single-session,
 * the file is absent (older turns), or unreadable. Works for both the live and any
 * historical session — it only needs (workspace_root, turn_id), the same direct-file
 * approach as readHistoricalSession. Agent/synthesis text is masked for display.
 */
export function readAgentReport(root: string | null, turnId: string | null | undefined): AgentReport | null {
  const id = (turnId ?? "").trim()
  if (!root || !id) return null
  const path = join(root, "agent_reports", `${id}.json`)
  if (!existsSync(path)) return null
  let raw: any
  try {
    raw = JSON.parse(readFileSync(path, "utf-8"))
  } catch {
    return null
  }
  const agents = Array.isArray(raw?.agents)
    ? raw.agents.map((a: any, i: number) => ({
        index: Number(a?.index ?? i),
        label: String(a?.label ?? `Agent ${i + 1}`),
        role: String(a?.role ?? ""),
        status: a?.status === "error" || a?.status === "timeout" ? a.status : "ok",
        text: maskSecrets(String(a?.text ?? "")),
        error: a?.error != null ? String(a.error) : null,
      }))
    : []
  return {
    turn_id: String(raw?.turn_id ?? id),
    et_date: String(raw?.et_date ?? ""),
    ts: String(raw?.ts ?? ""),
    turn_type: String(raw?.turn_type ?? "research"),
    mode: String(raw?.mode ?? ""),
    n_agents: Number(raw?.n_agents ?? agents.length),
    agents,
    synthesis: { text: maskSecrets(String(raw?.synthesis?.text ?? "")) },
  }
}

/** Step an ISO date string (YYYY-MM-DD) by ±1 day. */
export function shiftDate(etDate: string, days: number): string {
  const [y, m, d] = etDate.split("-").map(Number)
  const dt = new Date(Date.UTC(y!, m! - 1, d!))
  dt.setUTCDate(dt.getUTCDate() + days)
  return dt.toISOString().slice(0, 10)
}
