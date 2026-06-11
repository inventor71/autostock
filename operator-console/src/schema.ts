// F4 Unit B — TS mirror of Unit A's file-drop contract (E7/E8).
// Unit A (pydantic) is AUTHORITATIVE; keep these in sync via the cross-language contract
// test (test/contract.test.ts + tests/test_steering_contract.py, both against the golden
// contract/contract.json generated from the pydantic models). Field names & shapes must
// match `src/agent/steering/records.py` exactly.

export type SteeringVerb =
  | "buy" | "sell" | "flatten" | "flatten_all" | "stop"
  // F59: short shorthands — symmetric with buy/sell (short=open, cover=close)
  | "short" | "cover"
  | "pause" | "resume" | "halt_entries" | "allow_entries" | "kill"
  | "approve" | "reject" | "unlock" | "cancel"
  | "note" | "directive" | "directive_clear" | "answer"
  // F38: on-demand turn trigger (human starts a research turn between schedules)
  | "research"
  // F9 structured Alpaca-shaped order/management verbs (emitted by the new
  // structured MCP tools, NOT the deterministic parser).
  | "place_order" | "cancel_order" | "cancel_all" | "replace_order"
  | "close_position" | "close_all";
// Read-only verbs served entirely console-side (status/thesis/screening/...)
// live in parser.READ_VERBS, NOT here: this union is the file-drop contract
// the daemon validates, and read verbs never reach the channel.

// verbs that mutate the book/lifecycle → require human confirm before write (BR-B1)
export const TRADE_VERBS = new Set<SteeringVerb>(["buy", "sell", "short", "cover", "flatten", "flatten_all", "stop"]);
export const LIFECYCLE_VERBS = new Set<SteeringVerb>([
  "pause", "resume", "halt_entries", "allow_entries", "kill", "research",
]);
export const DESTRUCTIVE_VERBS = new Set<SteeringVerb>(["flatten_all", "kill"]); // require CONFIRM keyword

// E7 — written to steering/commands.jsonl (matches records.SteeringCommand)
export interface SteeringCommand {
  id: string; // uuid4 hex (no dashes), matches Unit A _new_id()
  ts: string; // ISO 8601
  verb: SteeringVerb;
  args: Record<string, unknown>;
  confirmed: boolean; // daemon rejects anything not true
  token: string; // operator token; never logged
  source: "human";
}

// E8 — read from steering/events.jsonl (matches records.SteeringEvent)
export interface SteeringEvent {
  id: string;
  corr_id: string | null;
  ts: string;
  kind: "outcome" | "fill" | "decision" | "pending" | "agent_question" | "lifecycle" | "reconcile" | "exec_outcome";
  payload: Record<string, unknown>;
}

export const TOKEN_ENV = "STEERING_OPERATOR_TOKEN";

// ---- runtime contract surface (checked against the golden by contract.test.ts) ---- #
// `satisfies` rejects any EXTRA/invalid entry; the `_Exhaustive` checks reject any
// MISSING one — together they pin each runtime list to its type both ways, so a verb/
// kind/field added to a type but not here (or vice versa) fails to compile.
export const ALL_VERBS = [
  "buy", "sell", "short", "cover", "flatten", "flatten_all", "stop",
  "pause", "resume", "halt_entries", "allow_entries", "kill",
  "approve", "reject", "unlock", "cancel",
  "note", "directive", "directive_clear", "answer",
  "research",
  "place_order", "cancel_order", "cancel_all", "replace_order",
  "close_position", "close_all",
] as const satisfies readonly SteeringVerb[];

// F9 (NFR-3) — per-verb structured arg names, pinned across languages by the
// golden contract (contract.json `command_args`). Sorted, so a renamed/typed
// field (e.g. trail_percent vs trail_pct) on either side fails contract.test.ts
// instead of being caught only at live order time. Must match
// records.PlaceOrderArgs + the daemon handlers' arg keys.
export const COMMAND_ARGS = {
  place_order: [
    "client_order_id", "extended_hours", "force", "limit_price", "notional",
    "order_class", "order_type", "qty", "side", "stop_loss", "stop_price",
    "symbol", "take_profit", "time_in_force", "trail_percent", "trail_price",
  ],
  cancel_order: ["order_id"],
  cancel_all: ["symbol"],
  replace_order: ["limit_price", "order_id", "qty", "stop_price", "time_in_force", "trail"],
  close_position: ["symbol"],
  close_all: ["cancel_orders"],
} as const;

export const ALL_EVENT_KINDS = [
  "outcome", "fill", "decision", "pending", "agent_question", "lifecycle", "reconcile",
  "exec_outcome",
] as const satisfies readonly SteeringEvent["kind"][];

export const COMMAND_FIELDS = [
  "id", "ts", "verb", "args", "confirmed", "token", "source",
] as const satisfies readonly (keyof SteeringCommand)[];

export const EVENT_FIELDS = [
  "id", "corr_id", "ts", "kind", "payload",
] as const satisfies readonly (keyof SteeringEvent)[];

type _VerbExhaustive = Exclude<SteeringVerb, (typeof ALL_VERBS)[number]> extends never ? true : never;
type _KindExhaustive = Exclude<SteeringEvent["kind"], (typeof ALL_EVENT_KINDS)[number]> extends never ? true : never;
type _CmdFieldsExhaustive = Exclude<keyof SteeringCommand, (typeof COMMAND_FIELDS)[number]> extends never ? true : never;
type _EvtFieldsExhaustive = Exclude<keyof SteeringEvent, (typeof EVENT_FIELDS)[number]> extends never ? true : never;
const _exhaustive: [_VerbExhaustive, _KindExhaustive, _CmdFieldsExhaustive, _EvtFieldsExhaustive] = [true, true, true, true];
void _exhaustive;
