import { Show, For, createMemo, createSignal } from "solid-js"
import type { MonitorDecision, MonitorTurn, AgentEval } from "../types"
import { OverlayPanel } from "./overlay-panel"
import { readAgentReport } from "../hooks/use-session-data"
import { actionColor, fmtCost, fmtDuration } from "../utils/format"

export interface TurnOverlayProps {
  turn: MonitorTurn
  decisions: MonitorDecision[]
  workspaceRoot?: string | null
  anchorX: number
  anchorY: number
  termWidth: number
  termHeight: number
  onClose: () => void
  onSymbolClick: (symbol: string, x: number, y: number) => void
}

const STATUS_MARK: Record<string, { ch: string; fg: string }> = {
  ok: { ch: "✓", fg: "green" },
  error: { ch: "✗", fg: "red" },
  timeout: { ch: "⏱", fg: "yellow" },
}

export function TurnOverlay(props: TurnOverlayProps) {
  // Source is the selected-date session (live or historical), passed in by the timeline.
  const turn = (): MonitorTurn | undefined => props.turn
  const decisions = (): MonitorDecision[] => props.decisions

  // F41: lazily read the persisted multi-agent evaluation for this turn (if any).
  // Re-reads when the turn id changes; null for single-session / older turns.
  const report = createMemo(() => readAgentReport(props.workspaceRoot ?? null, props.turn?.id))

  // Drill-down: which evaluation is open. -1 = synthesis, >=0 = agents[index], null = list view.
  const [open, setOpen] = createSignal<number | null>(null)

  // Unified, drillable entry list: each agent/round + a final "Synthesis" entry.
  const entries = createMemo(() => {
    const r = report()
    if (!r) return [] as AgentEval[]
    const list: AgentEval[] = [...r.agents]
    if (r.synthesis?.text) {
      list.push({
        index: -1, label: "Synthesis · final verdict", role: "",
        status: "ok", text: r.synthesis.text,
      })
    }
    return list
  })

  const selected = createMemo(() => {
    const i = open()
    if (i == null) return undefined
    return entries().find((e) => e.index === i)
  })

  const isDrill = () => selected() !== undefined

  // Drill-down needs room for full text; the list view stays compact.
  const width = () => (isDrill() ? Math.min(100, props.termWidth - 2) : 68)
  const maxHeight = () => (isDrill() ? Math.min(30, props.termHeight - 2) : 15)

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
      <Show when={turn()} fallback={<text fg="gray">Turn not found</text>}>
        {(t) => (
          <Show
            when={isDrill()}
            fallback={
              <box flexDirection="column">
                {/* Header */}
                <text fg="white"><b>[{t().id}]</b> <span style={{ fg: "gray" }}>{t().type} · {t().ts} · {fmtDuration(t().duration_ms)} · {fmtCost(t().cost_usd)} · {t().num_decisions} dec</span></text>
                {/* Summary */}
                <text fg="cyan">{t().summary}</text>
                {/* Decisions */}
                <Show when={decisions().length > 0}>
                  <text fg="gray">{"─".repeat(50)}</text>
                  <For each={decisions()}>
                    {(d) => (
                      <box>
                        <text fg={actionColor(d.action)}>{d.action.padEnd(11)}</text>
                        <text
                          fg="white"
                          onMouseUp={(evt: any) => {
                            props.onSymbolClick(d.symbol, evt.x ?? props.anchorX, evt.y ?? props.anchorY)
                            evt.stopPropagation?.()
                          }}
                        >
                          <b>{d.symbol}</b>
                        </text>
                        <text fg="gray">
                          {d.confidence != null ? ` (${d.confidence.toFixed(1)})` : ""} {d.reason}
                        </text>
                      </box>
                    )}
                  </For>
                </Show>
                {/* F41: multi-agent evaluations — click to drill into each one. */}
                <Show when={report()}>
                  {(r) => (
                    <box flexDirection="column">
                      <text fg="gray">{"─".repeat(50)}</text>
                      <text fg="gray">{r().mode} · {r().n_agents} agents — click to open:</text>
                      <For each={entries()}>
                        {(e) => {
                          const mark = STATUS_MARK[e.status] ?? STATUS_MARK.ok!
                          return (
                            <box
                              onMouseUp={(evt: any) => {
                                setOpen(e.index)
                                evt.stopPropagation?.()
                              }}
                            >
                              <text fg="cyan">{"› "}</text>
                              <text fg="white">{e.label}</text>
                              <text fg={mark.fg}>{"  " + mark.ch}</text>
                            </box>
                          )
                        }}
                      </For>
                    </box>
                  )}
                </Show>
              </box>
            }
          >
            {/* Drill-down view: one evaluation's full text, scrollable. */}
            {(() => {
              const e = selected()!
              return (
                <box flexDirection="column" flexGrow={1} minHeight={0}>
                  <box
                    onMouseUp={(evt: any) => {
                      setOpen(null)
                      evt.stopPropagation?.()
                    }}
                  >
                    <text fg="cyan">{"‹ back"}</text>
                    <text fg="white">{"   " + e.label}</text>
                  </box>
                  <Show when={e.role}>
                    <text fg="gray">{e.role}</text>
                  </Show>
                  <Show when={e.error}>
                    <text fg="red">{"error: " + e.error}</text>
                  </Show>
                  <text fg="gray">{"─".repeat(Math.min(width() - 4, 90))}</text>
                  <scrollbox flexGrow={1} minHeight={0}>
                    <For each={(e.text || "(no text)").split("\n")}>
                      {(line) => <text fg="white">{line}</text>}
                    </For>
                  </scrollbox>
                </box>
              )
            })()}
          </Show>
        )}
      </Show>
    </OverlayPanel>
  )
}
