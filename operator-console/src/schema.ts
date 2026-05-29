// F4 Unit B — TS mirror of Unit A's file-drop contract (E7/E8).
// Unit A (pydantic) is AUTHORITATIVE; keep these in sync via the contract test
// (test/contract.test.ts against ../../steering contract-samples). Field names &
// shapes must match `src/agent/steering/records.py` exactly.

export type SteeringVerb =
  | "buy" | "sell" | "flatten" | "flatten_all" | "stop"
  | "pause" | "resume" | "halt_entries" | "allow_entries" | "kill"
  | "approve" | "reject" | "unlock" | "cancel"
  | "note" | "directive" | "directive_clear" | "answer";

// verbs that mutate the book/lifecycle → require human confirm before write (BR-B1)
export const TRADE_VERBS = new Set<SteeringVerb>(["buy", "sell", "flatten", "flatten_all", "stop"]);
export const LIFECYCLE_VERBS = new Set<SteeringVerb>([
  "pause", "resume", "halt_entries", "allow_entries", "kill",
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
  kind: "outcome" | "fill" | "decision" | "pending" | "agent_question" | "lifecycle" | "reconcile";
  payload: Record<string, unknown>;
}

export const TOKEN_ENV = "STEERING_OPERATOR_TOKEN";
