import { For, Show, createMemo, createSignal, onCleanup } from "solid-js"
import type { HealthReport, HealthDimension } from "../types"
import { OverlayPanel } from "./overlay-panel"
import { healthGlyph, healthColor } from "../utils/format"

export interface HealthOverlayProps {
  report: HealthReport
  stale?: boolean
  // Latest publish time for the "age" line. Defaults to report.ts, but the caller
  // passes the live publish ts so age reflects the last publish, not the last verdict
  // change (which would inflate while a healthy daemon republishes the same verdict).
  ts?: string | null
  anchorX: number
  anchorY: number
  termWidth: number
  termHeight: number
  onClose: () => void
}

// F69: flat read-only view of the lightweight system-health report. Header shows the
// overall verdict + summary + relative age; body lists every dimension with its
// status glyph, and expands the non-green checks (name + detail/error) inline.
export function HealthOverlay(props: HealthOverlayProps) {
  const report = () => props.report
  const dims = createMemo<HealthDimension[]>(() =>
    Object.values(report().dimensions ?? {}).sort((a, b) => a.dimension.localeCompare(b.dimension)),
  )

  // Wall-clock tick so the relative age keeps counting up while the overlay is open
  // even with no new publish (the stalled-daemon case — otherwise "age" freezes while
  // the header already shows [STALE]).
  const [nowMs, setNowMs] = createSignal(Date.now())
  const ageTimer = setInterval(() => setNowMs(Date.now()), 30 * 1000)
  onCleanup(() => clearInterval(ageTimer))

  const age = createMemo(() => {
    const tsStr = props.ts ?? report().ts
    const ms = Date.parse(tsStr)
    if (Number.isNaN(ms)) return tsStr ?? ""
    const secs = Math.max(0, Math.round((nowMs() - ms) / 1000))
    if (secs < 90) return `${secs}s ago`
    return `${Math.round(secs / 60)}m ago`
  })

  const width = () => Math.min(72, props.termWidth - 2)
  const maxHeight = () => Math.min(24, props.termHeight - 2)

  const isBad = (s: string) => s !== "OK" && s !== "SKIPPED"

  return (
    <OverlayPanel
      anchorX={props.anchorX}
      anchorY={props.anchorY}
      width={width()}
      maxHeight={maxHeight()}
      termWidth={props.termWidth}
      termHeight={props.termHeight}
      onClose={props.onClose}
    >
      <box flexDirection="column">
        {/* Header: overall verdict */}
        <text>
          <span style={{ fg: healthColor(report().overall, props.stale) }}>
            {healthGlyph(report().overall, props.stale)}{" "}
          </span>
          <b>System Health</b>
          <span style={{ fg: "gray" }}>
            {"  "}[{props.stale ? "STALE" : report().overall}] · {age()}
          </span>
        </text>
        <text fg="cyan">{report().summary || "All checks passed."}</text>
        <text fg="gray">{"─".repeat(Math.min(60, width() - 4))}</text>

        {/* Dimensions */}
        <For each={dims()}>
          {(dim) => (
            <box flexDirection="column">
              <text>
                <span style={{ fg: healthColor(dim.status) }}>{healthGlyph(dim.status)} </span>
                <span style={{ fg: isBad(dim.status) ? "white" : "gray" }}>
                  {dim.dimension}
                </span>
                <span style={{ fg: "gray" }}>{"  " + dim.status}</span>
              </text>
              {/* Expand only the checks that aren't green/skipped. */}
              <For each={(dim.checks ?? []).filter((c) => isBad(c.status))}>
                {(c) => (
                  <text fg="gray">
                    {"    " + c.name + ": "}
                    <span style={{ fg: healthColor(c.status) }}>{c.detail || c.error || c.status}</span>
                  </text>
                )}
              </For>
            </box>
          )}
        </For>
        <text fg="gray">{"─".repeat(Math.min(60, width() - 4))}</text>
        <text fg="gray">click again or press Esc to close · full check: scripts/health.py</text>
      </box>
    </OverlayPanel>
  )
}
