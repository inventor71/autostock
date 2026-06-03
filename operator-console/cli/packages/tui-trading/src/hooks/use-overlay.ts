import { createSignal } from "solid-js"
import type { OverlayState, InterventionMarker } from "../types"

const CLOSED: OverlayState = {
  type: null, turnId: null, symbol: null, intervention: null, anchorX: 0, anchorY: 0,
}

export function createOverlayStore() {
  const [state, setState] = createSignal<OverlayState>(CLOSED)

  return {
    state,

    openTurn(turnId: string, x: number, y: number) {
      const cur = state()
      if (cur.type === "turn" && cur.turnId === turnId) {
        setState(CLOSED)
      } else {
        setState({ type: "turn", turnId, symbol: null, intervention: null, anchorX: x, anchorY: y })
      }
    },

    openSymbol(symbol: string, x: number, y: number) {
      const cur = state()
      if (cur.type === "symbol" && cur.symbol === symbol) {
        setState(CLOSED)
      } else {
        setState({ type: "symbol", turnId: null, symbol, intervention: null, anchorX: x, anchorY: y })
      }
    },

    openIntervention(iv: InterventionMarker, x: number, y: number) {
      const cur = state()
      if (cur.type === "intervention" && cur.intervention?.ts === iv.ts) {
        setState(CLOSED)
      } else {
        setState({ type: "intervention", turnId: null, symbol: null, intervention: iv, anchorX: x, anchorY: y })
      }
    },

    close() {
      setState(CLOSED)
    },
  }
}
