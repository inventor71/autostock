import { readFileSync } from "fs"
import { join } from "path"
import { createSignal, onCleanup } from "solid-js"
import type { MonitorData } from "../types"

// Signature of the fields the UI actually renders, EXCLUDING volatile ones
// (`ts` publish time, `log` tail) that the daemon rewrites every ~10s even when
// nothing meaningful changed. Updating the signal on those would recreate every
// timeline marker box each poll → visible flicker. We only push a new value when
// this signature changes.
function contentSig(d: MonitorData): string {
  return JSON.stringify({
    s: d.session_et_date,
    m: d.market,
    c: d.current_turn,
    t: d.turns,
    i: d.interventions,
    de: d.decisions,
    w: d.workspace_root,
  })
}

export function useMonitorData(steeringDir: string, intervalMs = 1500) {
  const [monitor, setMonitor] = createSignal<MonitorData | null>(null)
  let lastSig: string | null = null

  function poll(): void {
    let raw: string
    try {
      raw = readFileSync(join(steeringDir, "monitor.json"), "utf-8")
    } catch {
      // Transient read failure (e.g. file briefly missing) — keep the last good
      // value rather than flipping the whole bar to "disconnected".
      return
    }
    let data: MonitorData
    try {
      data = JSON.parse(raw) as MonitorData
    } catch {
      return // torn/partial — keep last good
    }
    const sig = contentSig(data)
    if (sig === lastSig) return // nothing the UI cares about changed → no churn
    lastSig = sig
    setMonitor(data)
  }

  poll()
  const timer = setInterval(poll, intervalMs)
  onCleanup(() => clearInterval(timer))

  return {
    monitor,
    currentTurn: () => monitor()?.current_turn ?? null,
    recentTurns: () => monitor()?.turns?.recent ?? [],
    recentDecisions: () => monitor()?.decisions ?? [],
    todayCount: () => monitor()?.turns?.today_count ?? 0,
    todayCost: () => monitor()?.turns?.today_cost_usd ?? 0,
    workspaceRoot: () => monitor()?.workspace_root ?? "",
  }
}
