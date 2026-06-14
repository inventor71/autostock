import { z } from "zod";

/**
 * Zod mirrors of the Python daemon artifacts. The Python side is authoritative:
 * every object is loose (unknown fields pass through) so daemon-side additions
 * never break viz-shell — only missing required fields fail (BR-9).
 *
 * Field sets verified against live files on 2026-06-13/14:
 *   steering/snapshot.json  — account.{equity,cash,invested,open_pnl,position_count},
 *                             positions = dict keyed by symbol (NOT an array),
 *                             open_orders[] / recent_fills[] / round_trip{} / run_state{}
 *   workspace/equity.jsonl  — one record per line: ts/equity/cash/... + benchmark map
 */

export const SnapshotPositionSchema = z
  .looseObject({
    qty: z.coerce.number(),
    avg_entry_price: z.coerce.number().optional(),
    side: z.string().optional(),
    current_price: z.coerce.number().optional(),
    market_value: z.coerce.number().optional(),
    unrealized_pnl: z.coerce.number().optional(),
  });

// One resting order (bracket/OCO leg). stop_price XOR limit_price by order_type.
export const OpenOrderSchema = z.looseObject({
  symbol: z.string(),
  order_id: z.string().optional(),
  side: z.string().optional(), // buy | sell
  order_type: z.string().optional(), // limit | stop | ...
  limit_price: z.coerce.number().nullish(),
  stop_price: z.coerce.number().nullish(),
  current_price: z.coerce.number().optional(),
});

export const RecentFillSchema = z.looseObject({
  ts: z.string(),
  side: z.string().optional(),
  qty: z.coerce.number().optional(),
  symbol: z.string(),
  price: z.coerce.number().optional(),
});

export const RoundTripSchema = z.looseObject({
  closed_count: z.coerce.number().optional(),
  win_rate: z.coerce.number().nullish(), // null until any round trip closes
  realized_pnl: z.coerce.number().optional(),
  as_of: z.string().optional(),
});

export const RunStateSchema = z.looseObject({
  paused: z.boolean().optional(),
  entries_halted: z.boolean().optional(),
  et_date: z.string().optional(),
});

export const SnapshotSchema = z.looseObject({
  account: z
    .looseObject({
      equity: z.number().optional(),
      cash: z.number().optional(),
      invested: z.number().optional(),
      open_pnl: z.number().optional(),
      position_count: z.number().optional(),
    })
    .optional(),
  positions: z.record(z.string(), SnapshotPositionSchema).default({}),
  open_orders: z.array(OpenOrderSchema).default([]),
  recent_fills: z.array(RecentFillSchema).default([]),
  round_trip: RoundTripSchema.optional(),
  run_state: RunStateSchema.optional(),
  market_open: z.boolean().optional(),
  published_at: z.string().optional(),
});

export type Snapshot = z.infer<typeof SnapshotSchema>;
export type SnapshotPosition = z.infer<typeof SnapshotPositionSchema>;
export type OpenOrder = z.infer<typeof OpenOrderSchema>;
export type RecentFill = z.infer<typeof RecentFillSchema>;
export type RoundTrip = z.infer<typeof RoundTripSchema>;
export type RunState = z.infer<typeof RunStateSchema>;

export const EquityRecordSchema = z.looseObject({
  ts: z.string(),
  equity: z.number(),
  benchmark: z.record(z.string(), z.number()).optional(),
});

export type EquityRecord = z.infer<typeof EquityRecordSchema>;

// workspace/decisions.jsonl — one agent decision per line (reason is the narrative).
export const DecisionSchema = z.looseObject({
  ts: z.string(),
  symbol: z.string(),
  action: z.string(), // BUY | SELL | HOLD | ADJUST_STOP | ...
  confidence: z.coerce.number().nullish(),
  sell_pct: z.coerce.number().nullish(),
  limit: z.coerce.number().nullish(),
  stop: z.coerce.number().nullish(),
  target: z.coerce.number().nullish(),
  thesis_ref: z.string().nullish(),
  valid_until: z.string().nullish(),
  reason: z.string().optional(),
});

// workspace/turns.jsonl — one agent turn per line (cost/tokens/summary).
export const TurnSchema = z.looseObject({
  turn_id: z.string().optional(),
  ts: z.string(),
  et_date: z.string().optional(),
  turn_type: z.string().optional(), // wake | research | intraday | eod | ...
  model: z.string().optional(),
  num_decisions: z.coerce.number().optional(),
  cost_usd: z.coerce.number().optional(),
  duration_ms: z.coerce.number().optional(),
  input_tokens: z.coerce.number().optional(),
  output_tokens: z.coerce.number().optional(),
  summary: z.string().optional(),
  health: z.string().optional(),
});

// workspace/trades.jsonl — one closed round trip per line.
export const TradeSchema = z.looseObject({
  symbol: z.string(),
  qty: z.coerce.number().optional(),
  entry_price: z.coerce.number().optional(),
  exit_price: z.coerce.number().optional(),
  opened_at: z.string().optional(),
  closed_at: z.string().optional(),
  realized_pnl: z.coerce.number().optional(),
  return_pct: z.coerce.number().optional(),
});

export type Decision = z.infer<typeof DecisionSchema>;
export type Turn = z.infer<typeof TurnSchema>;
export type Trade = z.infer<typeof TradeSchema>;

/** positions/<SYMBOL>.md thesis docs are opaque markdown — never parsed (E3). */
export type ThesisDoc = {
  symbol: string;
  markdown: string;
  mtimeMs: number;
  /** true when the stat-stable read exhausted retries (fail-honest flag). */
  stale: boolean;
};
