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
        <text fg="white">
          <b>{"✚ Human"}</b>{" "}
          <span style={{ fg: interventionColor(iv().verb) }}>{iv().verb}</span>
          {iv().symbol ? <span style={{ fg: "white" }}>{` ${iv().symbol}`}</span> : ""}
          <span style={{ fg: "gray" }}>{` · ${fmtLocalHhmm(iv().ts)}`}</span>
        </text>
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
