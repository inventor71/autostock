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
  // F6: deep-monitoring views served from steering/monitor.json (turn cost/activity,
  // recent decisions). `log` (above) also reads the monitor view's log tail.
  "turns", "decisions",
  // F29: project directory tree for supervisor codebase orientation
  "codebase",
  // F28: static UI legend — explain TUI elements (timeline/sidebar/status) in normal mode
  "ui-legend",
]);

const VERB_ALIASES: Record<string, SteeringVerb> = {
  "halt-entries": "halt_entries",
  "allow-entries": "allow_entries",
  // a distinct verb (NOT "directive clear") so a directive whose text starts
  // with "clear" is never hijacked into a clear-directives command (review #2).
  "directive-clear": "directive_clear",
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
  // must start with a letter (review #8): rejects bare "." / "-" / "A.-" that the
  // old [A-Za-z.\-]{1,10} accepted and passed through to the broker.
  if (!/^[A-Za-z][A-Za-z.\-]{0,9}$/.test(tok)) throw new ParseError(`bad symbol '${tok}'`);
  return tok.toUpperCase();
}

/** Parse a typed command line into a CommandDraft. Leading "/" optional. */
export function parseCommand(input: string): CommandDraft {
  const trimmed = input.trim().replace(/^\//, "");
  if (!trimmed) throw new ParseError("empty command");
  const parts = trimmed.split(/\s+/);
  let head = parts[0].toLowerCase();
  let rest = parts.slice(1);

  // two-word verb: only `flatten all` (unambiguous — "all" is not a tradeable symbol).
  // `directive clear` was REMOVED (review #2): use the `/directive-clear` alias so a
  // directive whose text begins with "clear" is recorded as a directive, not a clear.
  if (head === "flatten" && rest[0]?.toLowerCase() === "all" && rest.length === 1) {
    return mk("flatten_all", {}, "FLATTEN ALL positions + cancel all resting orders");
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
    // F38: /research — on-demand turn trigger (no args; confirm like other lifecycle verbs)
    case "research":
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
      // The arg is a SYMBOL (cancel its resting orders) OR a queued-trade id / id-PREFIX
      // (the sidebar's queued list shows an 8-char id). The daemon resolves which — a
      // unique queued-id prefix wins, else it's a symbol — so we just pass it through.
      const arg = rest[0];
      if (!arg) throw new ParseError("cancel needs a symbol or a queued-trade id");
      if (!/^[A-Za-z0-9.\-]{1,32}$/.test(arg)) throw new ParseError(`bad cancel target '${arg}'`);
      return mk("cancel", { target: arg }, `CANCEL ${arg}`);
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
    case "directive_clear": {
      const which = rest[0] ?? "all";
      return mk("directive_clear", { which }, `clear directive(s): ${which}`);
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
  // strict digits only (review #3): parseInt accepted "3abc"→3 and "3.9"→3,
  // letting a malformed id approve/reject the wrong pending item.
  if (!tok || !/^\d+$/.test(tok)) throw new ParseError(usage);
  return parseInt(tok, 10);
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
