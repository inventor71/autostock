import { Show, For } from "solid-js"
import type { MonitorDecision, MonitorTurn } from "../types"
import { OverlayPanel } from "./overlay-panel"
import { actionColor, fmtCost, fmtDuration } from "../utils/format"

export interface TurnOverlayProps {
  turn: MonitorTurn
  decisions: MonitorDecision[]
  anchorX: number
  anchorY: number
  termWidth: number
  termHeight: number
  onClose: () => void
  onSymbolClick: (symbol: string, x: number, y: number) => void
}

export function TurnOverlay(props: TurnOverlayProps) {
  // Source is the selected-date session (live or historical), passed in by the timeline.
  const turn = (): MonitorTurn | undefined => props.turn
  const decisions = (): MonitorDecision[] => props.decisions

  return (
    <OverlayPanel
      anchorX={props.anchorX}
      anchorY={props.anchorY}
      width={68}
      maxHeight={15}
      termWidth={props.termWidth}
      termHeight={props.termHeight}
      onClose={props.onClose}
    >
      <Show when={turn()} fallback={<text fg="gray">Turn not found</text>}>
        {(t) => (
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
          </box>
        )}
      </Show>
    </OverlayPanel>
  )
}
