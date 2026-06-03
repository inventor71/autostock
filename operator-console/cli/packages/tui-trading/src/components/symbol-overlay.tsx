import { Show, For } from "solid-js"
import type { MonitorData, MonitorDecision, PositionInfo } from "../types"
import { OverlayPanel } from "./overlay-panel"
import { readThesis } from "../hooks/use-thesis"
import { readPositions } from "../hooks/use-snapshot-data"
import { actionColor, fmtPnl } from "../utils/format"

export interface SymbolOverlayProps {
  symbol: string
  anchorX: number
  anchorY: number
  monitor: MonitorData
  steeringDir: string
  workspaceDir: string
  termWidth: number
  termHeight: number
  onClose: () => void
}

export function SymbolOverlay(props: SymbolOverlayProps) {
  const thesis = () => readThesis(props.workspaceDir, props.symbol)
  const position = (): PositionInfo | null => {
    const positions = readPositions(props.steeringDir)
    return positions[props.symbol] ?? null
  }
  const decisions = (): MonitorDecision[] =>
    props.monitor.decisions
      .filter((d) => d.symbol === props.symbol)
      .slice(-5)

  const thesisLines = () => {
    const md = thesis().markdown
    if (!md) return []
    return md.split("\n").slice(0, 10)
  }

  return (
    <OverlayPanel
      anchorX={props.anchorX}
      anchorY={props.anchorY}
      width={55}
      maxHeight={18}
      termWidth={props.termWidth}
      termHeight={props.termHeight}
      onClose={props.onClose}
    >
      <box flexDirection="column">
        {/* Header */}
        <text fg="white"><b>{props.symbol}</b></text>
        <Show when={position()}>
          {(pos) => {
            const pnl = fmtPnl(pos().unrealized_pnl)
            return (
              <text fg="gray">
                Qty: {pos().qty} · Entry: ${pos().avg_entry_price.toFixed(2)} · Current: ${pos().current_price.toFixed(2)} ·{" "}
                <text fg={pnl.color}>{pnl.text}</text>
              </text>
            )
          }}
        </Show>

        {/* Thesis */}
        <text fg="gray">{"─".repeat(50)}</text>
        <Show when={thesis().exists} fallback={<text fg="gray">No thesis file</text>}>
          <For each={thesisLines()}>
            {(line) => <text fg="white">{line}</text>}
          </For>
          <Show when={thesis().markdown.split("\n").length > 10}>
            <text fg="gray">... (truncated)</text>
          </Show>
        </Show>

        {/* Recent decisions */}
        <Show when={decisions().length > 0}>
          <text fg="gray">{"─".repeat(50)}</text>
          <text fg="gray">Recent:</text>
          <For each={decisions()}>
            {(d) => (
              <text>
                <text fg={actionColor(d.action)}>{d.action}</text>
                <text fg="gray">{d.turn_id ? `(${d.turn_id})` : ""} {d.ts}</text>
              </text>
            )}
          </For>
        </Show>
      </box>
    </OverlayPanel>
  )
}
