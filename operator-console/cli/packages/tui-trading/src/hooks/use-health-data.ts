import { readFileSync } from "fs"
import { join } from "path"
import { createSignal, onCleanup } from "solid-js"
import type { HealthReport } from "../types"

// F69: poll steering/health.json (written atomically by the daemon's publish_health
// via temp+os.replace, so a reader never sees a torn file — the JSON.parse guard is
// just a belt-and-suspenders safety net). Mirrors use-monitor-data.ts.

// Content signature EXCLUDING volatile fields. The daemon rewrites health.json every
// cadence even when the verdict is unchanged; per-check `duration_ms` and some
// `detail` strings (equity, market phase) drift every publish. Keying the signal on
// those would re-render the glyph/overlay each poll. We update only when the verdict
// — overall + per-dimension status + the set of non-green check names — changes.
function contentSig(h: HealthReport): string {
  const dims: Record<string, { s: string; f: string[] }> = {}
  for (const [name, dim] of Object.entries(h.dimensions ?? {})) {
    dims[name] = {
      s: dim.status,
      f: (dim.checks ?? [])
        .filter((c) => c.status !== "OK" && c.status !== "SKIPPED")
        .map((c) => c.name)
        .sort(),
    }
  }
  return JSON.stringify({ o: h.overall, d: dims })
}

// Fallback stale window when the daemon didn't stamp publish_interval_seconds.
const DEFAULT_STALE_MS = 20 * 60 * 1000

// How often stale()/age re-evaluate against the wall clock. The verdict signal only
// changes on a verdict change, so without this tick a daemon that stopped publishing
// would never flip the glyph to STALE (nothing else re-renders the binding).
const FRESHNESS_TICK_MS = 30 * 1000

export function useHealthData(steeringDir: string, intervalMs = 5000) {
  const [health, setHealth] = createSignal<HealthReport | null>(null)
  let lastSig: string | null = null
  // Freshness (publish time + cadence) is tracked in SIGNALS — separate from the
  // verdict-gated `health` signal — so a same-verdict republish doesn't churn the
  // glyph/overlay content, yet stale()/age stay reactive to the newest publish time.
  const [lastTs, setLastTs] = createSignal<string | null>(null)
  const [lastIntervalSec, setLastIntervalSec] = createSignal<number | null>(null)
  // Wall-clock tick so stale()/age re-evaluate over time even with NO new publish
  // (the dead-daemon case: nothing else would ever re-render the glyph).
  const [now, setNow] = createSignal(Date.now())

  function poll(): void {
    let raw: string
    try {
      raw = readFileSync(join(steeringDir, "health.json"), "utf-8")
    } catch {
      // File missing (steering off / not published yet) — keep the last good value
      // rather than flipping the glyph to "no data" on a transient miss.
      return
    }
    let data: HealthReport
    try {
      data = JSON.parse(raw) as HealthReport
    } catch {
      return // torn/partial — keep last good
    }
    // Track freshness every poll regardless of verdict change. setSignal is a no-op
    // when the value is unchanged, so a same-ts re-read won't trigger a re-render.
    if (data.ts) setLastTs(data.ts)
    if (data.publish_interval_seconds != null) setLastIntervalSec(data.publish_interval_seconds)
    const sig = contentSig(data)
    if (sig === lastSig) return // verdict unchanged → don't churn the report signal
    lastSig = sig
    setHealth(data)
  }

  // Reactive: reads the freshness signals + the wall-clock tick, so callers that
  // render stale() re-evaluate both on a new publish and as time passes.
  function stale(): boolean {
    const ts = lastTs()
    if (!ts) return false
    const ms = Date.parse(ts)
    if (Number.isNaN(ms)) return false
    const win = lastIntervalSec()
    const windowMs = win ? win * 3 * 1000 : DEFAULT_STALE_MS
    return now() - ms > windowMs
  }

  poll()
  const timer = setInterval(poll, intervalMs)
  const tick = setInterval(() => setNow(Date.now()), FRESHNESS_TICK_MS)
  onCleanup(() => { clearInterval(timer); clearInterval(tick) })

  return {
    health,
    stale,
    overall: () => health()?.overall ?? null,
    // Latest publish time (reactive) — the overlay uses this for "age" instead of the
    // verdict-gated report.ts, which would inflate while a healthy daemon republishes.
    lastTs,
  }
}
