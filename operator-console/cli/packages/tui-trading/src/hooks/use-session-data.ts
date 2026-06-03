import { readFileSync, existsSync } from "fs"
import { join } from "path"
import type { MonitorData, MonitorTurn, InterventionMarker } from "../types"

// F25 FR-2: resolve a session's turns + interventions for a given ET date.
// The current/upcoming session comes straight from monitor.json (live). For any
// other date the TUI reads turns.jsonl / human_directives.jsonl directly and
// filters by et_date — giving unlimited history (Q4=C) with no request channel.

export interface SessionData {
  turns: MonitorTurn[]
  interventions: InterventionMarker[]
}

const TRADE_VERBS = new Set([
  "buy", "sell", "flatten", "flatten_all", "place_order",
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
  if (!monitor) return { turns: [], interventions: [] }

  // Live session: use the already-filtered monitor payload.
  if (etDate === monitor.session_et_date) {
    return {
      turns: monitor.turns?.recent ?? [],
      interventions: monitor.interventions ?? [],
    }
  }

  // Historical: read files directly and filter by ET date.
  const root = monitor.workspace_root
  if (!root) return { turns: [], interventions: [] }

  const turns: MonitorTurn[] = readJsonl(join(root, "turns.jsonl"))
    .filter((r) => recordEtDate(r) === etDate)
    .map((r) => ({
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

  return { turns, interventions }
}

/** Step an ISO date string (YYYY-MM-DD) by ±1 day. */
export function shiftDate(etDate: string, days: number): string {
  const [y, m, d] = etDate.split("-").map(Number)
  const dt = new Date(Date.UTC(y!, m! - 1, d!))
  dt.setUTCDate(dt.getUTCDate() + days)
  return dt.toISOString().slice(0, 10)
}
