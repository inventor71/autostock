export interface MonitorData {
  ts: string
  current_turn: CurrentTurn | null
  workspace_root: string | null
  // F25: market-aware timeline metadata.
  market?: MarketRule
  session_et_date?: string
  turns: TurnsBlock
  decisions: MonitorDecision[]
  interventions?: InterventionMarker[]
  log: string[]
}

// F25: market-session rule (wall-clock ET times). The TUI converts to the
// operator's local timezone using the IANA tz, so DST is handled by Intl.
export interface MarketRule {
  tz: string
  pre_open: string       // "HH:MM"
  regular_open: string
  regular_close: string
  after_close: string
}

export const DEFAULT_MARKET_RULE: MarketRule = {
  tz: "America/New_York",
  pre_open: "04:00",
  regular_open: "09:30",
  regular_close: "16:00",
  after_close: "20:00",
}

// F25: a trade-only human intervention shown on the timeline (FR-3).
export interface InterventionMarker {
  ts: string            // tz-aware ISO
  et_date: string
  verb: string
  symbol: string | null
  outcome: string
  detail: string
}

export interface CurrentTurn {
  id: string
  type: string
  started_at: string
}

export interface TurnsBlock {
  today_count: number
  today_cost_usd: number
  recent: MonitorTurn[]
}

export interface MonitorTurn {
  id: string
  type: TurnType
  ts: string             // F25: full tz-aware ISO (was HH:MM)
  et_date?: string
  cost_usd: number
  num_decisions: number
  duration_ms: number | null
  summary: string
  health: "ok" | "error"
}

export interface MonitorDecision {
  turn_id: string | null
  ts: string
  symbol: string
  action: "BUY" | "SELL" | "HOLD" | "ADJUST_STOP"
  confidence: number | null
  reason: string
  source: "agent" | "human"
}

export type TurnType = "research" | "intraday" | "wake" | "eod" | "reconcile"

export interface PositionInfo {
  qty: number
  avg_entry_price: number
  current_price: number
  market_value: number
  unrealized_pnl: number
}

export interface OverlayState {
  type: "turn" | "symbol" | "intervention" | null
  turnId: string | null
  symbol: string | null
  intervention: InterventionMarker | null
  anchorX: number
  anchorY: number
}
