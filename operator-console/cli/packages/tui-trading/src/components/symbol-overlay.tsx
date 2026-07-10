import { Show, For } from "solid-js"
import type { MonitorData, MonitorDecision, PositionInfo } from "../types"
import { OverlayPanel } from "./overlay-panel"
import { readThesis } from "../hooks/use-thesis"
import { readPositions } from "../hooks/use-snapshot-data"
import { useQuote } from "../hooks/use-quote"
import { actionColor, fmtPnl, fmtLocalHhmm } from "../utils/format"

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
  // F95: live quote from the daemon warm cache (steering/quotes.json). Always
  // shown — for any clicked symbol, held or not — polling so it stays current
  // while the panel is open.
  const quote = useQuote(props.steeringDir, () => props.symbol)
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
        {/* F95: live quote — always shown (loading / price+as-of / unavailable). */}
        <Show
          when={quote()}
          fallback={<text fg="gray">시세 조회 중…</text>}
        >
          {(q) => (
            <Show
              when={q().price != null}
              fallback={<text fg="gray">시세 없음</text>}
            >
              <text fg="yellow">
                ${q().price!.toFixed(2)}{" "}
                <text fg="gray">· as of {fmtLocalHhmm(q().ts)}</text>
              </text>
            </Show>
          )}
        </Show>
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
