import type { JSX } from "solid-js"

export interface OverlayPanelProps {
  anchorX: number
  anchorY: number
  width?: number
  maxHeight?: number
  termWidth: number
  termHeight: number
  onClose: () => void
  children: JSX.Element
}

export function OverlayPanel(props: OverlayPanelProps) {
  const w = () => props.width ?? 50
  const maxH = () => props.maxHeight ?? 15

  const x = () => {
    let px = props.anchorX
    if (px + w() > props.termWidth) px = props.termWidth - w() - 1
    if (px < 0) px = 0
    return px
  }

  const y = () => {
    let py = props.anchorY + 1
    if (py + maxH() > props.termHeight) py = props.anchorY - maxH()
    if (py < 0) py = 0
    return py
  }

  return (
    <box
      width={props.termWidth}
      height={props.termHeight}
      position="absolute"
      zIndex={2000}
      onMouseUp={(evt: any) => {
        props.onClose()
        evt.stopPropagation?.()
      }}
    >
      {/* Content panel — backgroundColor fills the box area adaptively */}
      <box
        position="absolute"
        left={x()}
        top={y()}
        width={w()}
        maxHeight={maxH()}
        borderStyle="rounded"
        backgroundColor="#2d2d3f"
        paddingLeft={1}
        paddingRight={1}
        onMouseUp={(evt: any) => evt.stopPropagation?.()}
      >
        {props.children}
      </box>
    </box>
  )
}
