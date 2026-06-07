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

export function useHealthData(steeringDir: string, intervalMs = 5000) {
  const [health, setHealth] = createSignal<HealthReport | null>(null)
  let lastSig: string | null = null
  // Freshness is tracked OUTSIDE the signal so a same-verdict republish doesn't
  // churn the glyph/overlay, while stale() still sees the newest publish time.
  let lastTs: string | null = null
  let lastIntervalSec: number | null = null

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
    // Track freshness every poll regardless of verdict change.
    lastTs = data.ts ?? lastTs
    lastIntervalSec = data.publish_interval_seconds ?? lastIntervalSec
    const sig = contentSig(data)
    if (sig === lastSig) return // verdict unchanged → no re-render
    lastSig = sig
    setHealth(data)
  }

  // Time-based; recomputed by callers via the accessor (not a signal).
  function stale(): boolean {
    if (!lastTs) return false
    const ms = Date.parse(lastTs)
    if (Number.isNaN(ms)) return false
    const windowMs = lastIntervalSec ? lastIntervalSec * 3 * 1000 : DEFAULT_STALE_MS
    return Date.now() - ms > windowMs
  }

  poll()
  const timer = setInterval(poll, intervalMs)
  onCleanup(() => clearInterval(timer))

  return {
    health,
    stale,
    overall: () => health()?.overall ?? null,
  }
}
