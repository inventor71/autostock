// F4 Unit B — deterministic command parser (BR-B5). The LLM-bypass path: a typed
// slash/keystroke command is reduced to a CommandDraft here with NO model in the
// loop. NL input goes through the LLM to produce args, but is validated by THIS
// same parser before becoming a draft. Fail-closed: invalid → ParseError, never a
// partial/guessed action.

import { DESTRUCTIVE_VERBS, type SteeringVerb, TRADE_VERBS } from "./schema";

export class ParseError extends Error {}

export interface CommandDraft {
  verb: SteeringVerb;
  args: Record<string, unknown>;
  echo: string; // 1-line human-readable interpretation
  confirmRequired: boolean; // trade/lifecycle/approval → confirm before write
  destructive: boolean; // flatten_all/kill → CONFIRM keyword
  readOnly: boolean; // status/positions/... → no write, no confirm
}

// read-only introspection verbs (served by deterministic reads, not file-drop)
export const READ_VERBS = new Set([
  "status", "positions", "book", "orders", "log", "agent-trace", "why",
  "pending", "directives", "help", "inbox",
]);

const VERB_ALIASES: Record<string, SteeringVerb> = {
  "halt-entries": "halt_entries",
  "allow-entries": "allow_entries",
};

interface Size { size: number; unit: "$" | "sh" | "%"; }

function parseSize(tok: string | undefined, allowed: Array<Size["unit"]>): Size {
  if (!tok) throw new ParseError("size required, e.g. 1000$ | 5sh | 50%");
  const m = tok.match(/^(\d+(?:\.\d+)?)(\$|sh|%)$/);
  if (!m) throw new ParseError(`bad size '${tok}': use a number + ${allowed.join(" | ")}`);
  const size = parseFloat(m[1]);
  const unit = m[2] as Size["unit"];
  if (size <= 0) throw new ParseError("size must be > 0");
  if (!allowed.includes(unit)) throw new ParseError(`unit '${unit}' not allowed here (use ${allowed.join(" | ")})`);
  return { size, unit };
}

function sym(tok: string | undefined): string {
  if (!tok) throw new ParseError("symbol required");
  if (!/^[A-Za-z.\-]{1,10}$/.test(tok)) throw new ParseError(`bad symbol '${tok}'`);
  return tok.toUpperCase();
}

/** Parse a typed command line into a CommandDraft. Leading "/" optional. */
export function parseCommand(input: string): CommandDraft {
  const trimmed = input.trim().replace(/^\//, "");
  if (!trimmed) throw new ParseError("empty command");
  const parts = trimmed.split(/\s+/);
  let head = parts[0].toLowerCase();
  let rest = parts.slice(1);

  // two-word verbs
  if (head === "flatten" && rest[0]?.toLowerCase() === "all") {
    return mk("flatten_all", {}, "FLATTEN ALL positions + cancel all resting orders");
  }
  if (head === "directive" && rest[0]?.toLowerCase() === "clear") {
    return mk("directive_clear", { which: rest[1] ?? "all" }, `clear directive(s): ${rest[1] ?? "all"}`);
  }
  head = VERB_ALIASES[head] ?? head;

  if (READ_VERBS.has(head)) {
    return { verb: head as SteeringVerb, args: { raw: trimmed }, echo: head, confirmRequired: false, destructive: false, readOnly: true };
  }

  switch (head as SteeringVerb) {
    case "buy": {
      const symbol = sym(rest[0]);
      const { size, unit } = parseSize(rest[1], ["$", "sh"]);
      return mk("buy", { symbol, size, unit }, `BUY ${size}${unit} ${symbol} @ market`);
    }
    case "sell": {
      const symbol = sym(rest[0]);
      const { size, unit } = parseSize(rest[1], ["%", "sh", "$"]);
      return mk("sell", { symbol, size, unit }, `SELL ${size}${unit} ${symbol} @ market`);
    }
    case "flatten": {
      const symbol = sym(rest[0]);
      return mk("flatten", { symbol }, `FLATTEN ${symbol} (close + cancel resting)`);
    }
    case "stop": {
      const symbol = sym(rest[0]);
      const price = parseFloat(rest[1] ?? "");
      if (!(price > 0)) throw new ParseError("stop price required (> 0)");
      return mk("stop", { symbol, price }, `STOP ${symbol} -> ${price}`);
    }
    case "pause": case "resume": case "halt_entries": case "allow_entries": case "kill":
      return mk(head as SteeringVerb, {}, head.replace("_", "-"));
    case "approve": {
      const id = intArg(rest[0], "approve <id>");
      return mk("approve", { id }, `APPROVE #${id}`);
    }
    case "reject": {
      const id = intArg(rest[0], "reject <id> [reason]");
      const reason = rest.slice(1).join(" ");
      return mk("reject", { id, reason }, `REJECT #${id}${reason ? ` (${reason})` : ""}`);
    }
    case "unlock": {
      const symbol = sym(rest[0]);
      return mk("unlock", { symbol }, `UNLOCK ${symbol}`);
    }
    case "cancel": {
      const symbol = sym(rest[0]);
      return mk("cancel", { symbol }, `CANCEL open orders for ${symbol}`);
    }
    case "note": {
      const text = rest.join(" ");
      if (!text) throw new ParseError("note text required");
      // notes apply without confirmation (context only)
      return { verb: "note", args: { text }, echo: `note: ${text}`, confirmRequired: false, destructive: false, readOnly: false };
    }
    case "directive": {
      const text = rest.join(" ");
      if (!text) throw new ParseError("directive text required");
      return mk("directive", { text }, `directive: ${text}`);
    }
    case "answer": {
      const id = rest[0];
      const text = rest.slice(1).join(" ");
      if (!id || !text) throw new ParseError("answer <question-id> <text>");
      return mk("answer", { id, text }, `answer ${id}: ${text}`);
    }
    default:
      throw new ParseError(`unknown command '${head}' (try /help)`);
  }
}

function intArg(tok: string | undefined, usage: string): number {
  const n = parseInt(tok ?? "", 10);
  if (!Number.isInteger(n)) throw new ParseError(usage);
  return n;
}

function mk(verb: SteeringVerb, args: Record<string, unknown>, echo: string): CommandDraft {
  return {
    verb, args, echo,
    confirmRequired: true, // trades/lifecycle/approval/directive/answer all confirm before write
    destructive: DESTRUCTIVE_VERBS.has(verb),
    readOnly: false,
  };
}

export { TRADE_VERBS };
