// F6 — sidebar width as a single shared reactive signal (critic #7: independent of
// sidebarVisible; Sidebar.width AND index.tsx contentWidth subscribe to THIS one signal,
// so the two can never diverge). The drag handle (sidebar.tsx) updates it; the value is
// persisted to a console-only XDG state file so a resize survives restart (FR-1.1).
//
// Priority on load: saved (ui.json) > AUTOSTOCK_SIDEBAR_WIDTH env > 42.

import { createSignal } from "solid-js"
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"

// F8: floor raised 24 -> 36 so the status.py-rich one-line rows (symbol · qty · price ·
// signed P&L%) stay readable instead of collapsing into an unreadable word-wrapped stack
// at very narrow widths. Drag wider for the fuller multi-field view.
export const MIN_SIDEBAR_WIDTH = 36
const FALLBACK_WIDTH = 42
const MIN_CONTENT = 20 // keep at least this many cols for the main pane

function stateFile(): string {
  const base = process.env["XDG_STATE_HOME"] || join(homedir(), ".local", "state")
  return join(base, "autostock-console", "ui.json")
}

/** Clamp to [MIN, max]. `maxAvail` (terminal width) bounds it so the main pane keeps
 *  at least MIN_CONTENT cols; non-finite input falls back to the default. */
export function clampWidth(n: number, maxAvail?: number): number {
  if (!Number.isFinite(n)) return FALLBACK_WIDTH
  const upper = maxAvail && maxAvail > MIN_CONTENT + MIN_SIDEBAR_WIDTH ? maxAvail - MIN_CONTENT : 200
  return Math.max(MIN_SIDEBAR_WIDTH, Math.min(Math.floor(n), upper))
}

function loadWidth(): number {
  try {
    const saved = JSON.parse(readFileSync(stateFile(), "utf8"))?.sidebarWidth
    if (Number.isFinite(saved)) return clampWidth(saved)
  } catch {
    /* no/!corrupt state file → fall through to env/default (fail-safe) */
  }
  const env = Number(process.env["AUTOSTOCK_SIDEBAR_WIDTH"])
  if (Number.isFinite(env) && env >= MIN_SIDEBAR_WIDTH && env <= 120) return Math.floor(env)
  return FALLBACK_WIDTH
}

const [sidebarWidth, setWidthSignal] = createSignal(loadWidth())
export { sidebarWidth }

let saveTimer: ReturnType<typeof setTimeout> | undefined
function persist(width: number): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try {
      const path = stateFile()
      mkdirSync(dirname(path), { recursive: true })
      const tmp = `${path}.${process.pid}.tmp`
      writeFileSync(tmp, JSON.stringify({ sidebarWidth: width }), "utf8")
      renameSync(tmp, path) // atomic
    } catch {
      /* persistence is best-effort; a failed save never disrupts the UI */
    }
  }, 250)
}

/** Set the sidebar width (clamped) and debounce-persist it. `maxAvail` = terminal width. */
export function setSidebarWidth(n: number, maxAvail?: number): void {
  const w = clampWidth(n, maxAvail)
  setWidthSignal(w)
  persist(w)
}
