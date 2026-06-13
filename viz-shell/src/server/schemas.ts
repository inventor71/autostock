import { z } from "zod";

/**
 * Zod mirrors of the Python daemon artifacts. The Python side is authoritative:
 * every object is loose (unknown fields pass through) so daemon-side additions
 * never break viz-shell — only missing required fields fail (BR-9).
 *
 * Field sets verified against live files on 2026-06-13:
 *   steering/snapshot.json  — account.{equity,cash,invested,open_pnl,position_count},
 *                             positions = dict keyed by symbol (NOT an array)
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
  market_open: z.boolean().optional(),
  published_at: z.string().optional(),
});

export type Snapshot = z.infer<typeof SnapshotSchema>;
export type SnapshotPosition = z.infer<typeof SnapshotPositionSchema>;

export const EquityRecordSchema = z.looseObject({
  ts: z.string(),
  equity: z.number(),
  benchmark: z.record(z.string(), z.number()).optional(),
});

export type EquityRecord = z.infer<typeof EquityRecordSchema>;

/** positions/<SYMBOL>.md thesis docs are opaque markdown — never parsed (E3). */
export type ThesisDoc = {
  symbol: string;
  markdown: string;
  mtimeMs: number;
  /** true when the stat-stable read exhausted retries (fail-honest flag). */
  stale: boolean;
};
