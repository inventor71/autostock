import { createSignal } from "solid-js"
import type { OverlayState, MonitorTurn, MonitorDecision, InterventionMarker, HealthReport } from "../types"

const CLOSED: OverlayState = {
  type: null, turn: null, decisions: [], symbol: null, intervention: null, health: null, anchorX: 0, anchorY: 0,
}

export function createOverlayStore() {
  const [state, setState] = createSignal<OverlayState>(CLOSED)

  return {
    state,

    openTurn(turn: MonitorTurn, decisions: MonitorDecision[], x: number, y: number) {
      const cur = state()
      if (cur.type === "turn" && cur.turn?.id === turn.id) {
        setState(CLOSED)
      } else {
        setState({ type: "turn", turn, decisions, symbol: null, intervention: null, health: null, anchorX: x, anchorY: y })
      }
    },

    openSymbol(symbol: string, x: number, y: number) {
      const cur = state()
      if (cur.type === "symbol" && cur.symbol === symbol) {
        setState(CLOSED)
      } else {
        setState({ type: "symbol", turn: null, decisions: [], symbol, intervention: null, health: null, anchorX: x, anchorY: y })
      }
    },

    openIntervention(iv: InterventionMarker, x: number, y: number) {
      const cur = state()
      if (cur.type === "intervention" && cur.intervention?.ts === iv.ts) {
        setState(CLOSED)
      } else {
        setState({ type: "intervention", turn: null, decisions: [], symbol: null, intervention: iv, health: null, anchorX: x, anchorY: y })
      }
    },

    // F69: toggle the system-health overlay (click-to-open, like turn/symbol).
    openHealth(health: HealthReport, x: number, y: number) {
      const cur = state()
      if (cur.type === "health") {
        setState(CLOSED)
      } else {
        setState({ type: "health", turn: null, decisions: [], symbol: null, intervention: null, health, anchorX: x, anchorY: y })
      }
    },

    close() {
      setState(CLOSED)
    },
  }
}
