import { expect, test } from "bun:test";
import { type CommandDraft, ParseError, parseCommand } from "../src/parser";

const ok = (s: string): CommandDraft => parseCommand(s);

test("lifecycle verbs", () => {
  expect(ok("/pause").verb).toBe("pause");
  expect(ok("resume").verb).toBe("resume"); // leading slash optional
  expect(ok("/halt-entries").verb).toBe("halt_entries");
  expect(ok("/allow-entries").verb).toBe("allow_entries");
});

test("F38 /research — on-demand turn trigger (no args, confirm-required)", () => {
  const d = ok("/research");
  expect(d.verb).toBe("research");
  expect(d.args).toEqual({});
  expect(d.confirmRequired).toBe(true);
  expect(d.readOnly).toBe(false);
});

test("sell with % / sh / $ and symbol uppercased", () => {
  const d = ok("/sell aapl 50%");
  expect(d.verb).toBe("sell");
  expect(d.args).toEqual({ symbol: "AAPL", size: 50, unit: "%" });
  expect(d.confirmRequired).toBe(true);
  expect(ok("/sell MSFT 5sh").args).toEqual({ symbol: "MSFT", size: 5, unit: "sh" });
  expect(ok("/sell MSFT 200$").args).toEqual({ symbol: "MSFT", size: 200, unit: "$" });
});

test("buy only allows $ or sh (not %)", () => {
  expect(ok("/buy AAPL 1000$").args).toEqual({ symbol: "AAPL", size: 1000, unit: "$" });
  expect(ok("/buy AAPL 5sh").args).toEqual({ symbol: "AAPL", size: 5, unit: "sh" });
  expect(() => ok("/buy AAPL 50%")).toThrow(ParseError); // % not allowed on buy
});

test("flatten all is destructive; flatten <sym> is not", () => {
  expect(ok("/flatten all")).toMatchObject({ verb: "flatten_all", destructive: true });
  expect(ok("/flatten AAPL")).toMatchObject({ verb: "flatten", destructive: false, args: { symbol: "AAPL" } });
  expect(ok("/kill").destructive).toBe(true);
});

test("approve / reject / unlock / stop", () => {
  expect(ok("/approve 3").args).toEqual({ id: 3 });
  expect(ok("/reject 3 too risky").args).toEqual({ id: 3, reason: "too risky" });
  expect(ok("/unlock NVDA").args).toEqual({ symbol: "NVDA" });
  expect(ok("/stop AAPL 230.5").args).toEqual({ symbol: "AAPL", price: 230.5 });
});

test("read-only verbs are flagged, no confirm", () => {
  const d = ok("/status");
  expect(d.readOnly).toBe(true);
  expect(d.confirmRequired).toBe(false);
});

test("F28: /ui-legend is a read verb; element kept in raw (no parser split)", () => {
  const d = ok("/ui-legend topbar.today_cost");
  expect(d.verb).toBe("ui-legend");
  expect(d.readOnly).toBe(true);
  expect(d.confirmRequired).toBe(false);
  // READ_VERBS pass the whole line as args.raw; the handler extracts the element.
  expect(d.args.raw).toBe("ui-legend topbar.today_cost");
  expect(ok("/ui-legend").verb).toBe("ui-legend"); // bare form ok
});

test("note applies without confirm; directive/answer confirm", () => {
  expect(ok("/note watch CPI")).toMatchObject({ verb: "note", confirmRequired: false });
  expect(ok("/directive be defensive")).toMatchObject({ verb: "directive", confirmRequired: true });
  expect(ok("/answer q1 stand down").args).toEqual({ id: "q1", text: "stand down" });
});

test("fail-closed on bad/missing/unknown", () => {
  expect(() => ok("")).toThrow(ParseError);
  expect(() => ok("/buy")).toThrow(ParseError); // no symbol
  expect(() => ok("/buy AAPL")).toThrow(ParseError); // no size
  expect(() => ok("/buy AAPL 1000")).toThrow(ParseError); // no unit
  expect(() => ok("/sell AAPL 0%")).toThrow(ParseError); // size > 0
  expect(() => ok("/frobnicate AAPL")).toThrow(ParseError); // unknown verb
});

test("/cancel passes the target through (daemon resolves id-prefix vs symbol)", () => {
  expect(ok("/cancel a1187da8").args).toEqual({ target: "a1187da8" }); // 8-char id prefix
  expect(ok("/cancel " + "a".repeat(32)).args).toEqual({ target: "a".repeat(32) }); // full id
  expect(ok("/cancel AAPL").args).toEqual({ target: "AAPL" }); // symbol
  expect(ok("/cancel a1187da8").verb).toBe("cancel");
  expect(() => ok("/cancel")).toThrow(ParseError); // arg required
});
