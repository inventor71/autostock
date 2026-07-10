import { Show } from "solid-js"
import type { InterventionMarker } from "../types"
import { OverlayPanel } from "./overlay-panel"
import { interventionColor, fmtLocalHhmm } from "../utils/format"

export interface InterventionOverlayProps {
  intervention: InterventionMarker
  anchorX: number
  anchorY: number
  termWidth: number
  termHeight: number
  onClose: () => void
  // F95: click the symbol to open its info panel (quote + position/thesis).
  onSymbolClick?: (symbol: string, x: number, y: number) => void
}

// F25 FR-3: detail popup for a human trade intervention.
export function InterventionOverlay(props: InterventionOverlayProps) {
  const iv = () => props.intervention
  return (
    <OverlayPanel
      anchorX={props.anchorX}
      anchorY={props.anchorY}
      width={60}
      maxHeight={8}
      termWidth={props.termWidth}
      termHeight={props.termHeight}
      onClose={props.onClose}
    >
      <box flexDirection="column">
        {/* Header row — inline text pieces; the symbol is its own clickable
            <text> (F95), mirroring the turn overlay's onMouseUp pattern. */}
        <box>
          <text fg="white"><b>{"✚ Human"}</b></text>
          <text fg={interventionColor(iv().verb)}>{` ${iv().verb}`}</text>
          <Show when={iv().symbol}>
            <text
              fg="white"
              onMouseUp={(evt: any) => {
                props.onSymbolClick?.(iv().symbol!, evt.x ?? props.anchorX, evt.y ?? props.anchorY)
                evt.stopPropagation?.()
              }}
            >
              {` ${iv().symbol}`}
            </text>
          </Show>
          <text fg="gray">{` · ${fmtLocalHhmm(iv().ts)}`}</text>
        </box>
        <Show when={iv().outcome}>
          <text fg="gray">{`outcome: ${iv().outcome}`}</text>
        </Show>
        <Show when={iv().detail}>
          <text fg="white">{iv().detail}</text>
        </Show>
      </box>
    </OverlayPanel>
  )
}
