// F21: L1 zod .refine() cross-field validation + L2 degenerate check tests.
// Run from operator-console/: bun test test/f21-validation.test.ts

import { describe, expect, test } from "bun:test";
import {
  isDegenerate,
  validatePlaceOrderArgs,
  validateReplaceOrderArgs,
} from "../src/steer-handler";

// --- L2 degenerate check -------------------------------------------------------- #

describe("isDegenerate", () => {
  test("0.01 is degenerate", () => expect(isDegenerate(0.01)).toBe(true));
  test("0 is NOT degenerate (non-positive)", () => expect(isDegenerate(0)).toBe(false));
  test("0.001 is degenerate (≤ threshold)", () => expect(isDegenerate(0.001)).toBe(true));
  test("1.0 is NOT degenerate", () => expect(isDegenerate(1.0)).toBe(false));
  test("undefined is NOT degenerate", () => expect(isDegenerate(undefined)).toBe(false));
  test("null is NOT degenerate", () => expect(isDegenerate(null)).toBe(false));
  test("negative is NOT degenerate", () => expect(isDegenerate(-0.01)).toBe(false));
  test("string is NOT degenerate", () => expect(isDegenerate("0.01")).toBe(false));
});

describe("validatePlaceOrderArgs", () => {
  test("valid args with qty only: no error", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, order_type: "market" })).toBeNull();
  });

  test("valid args with notional: no error", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", notional: 500, order_type: "market" })).toBeNull();
  });

  test("valid args with bracket legs: no error", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, take_profit: 200, stop_loss: 190 })).toBeNull();
  });

  test("valid trailing_stop with trail_price: no error (critic fix)", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, order_type: "trailing_stop", trail_price: 150 })).toBeNull();
  });

  test("degenerate take_profit 0.01: rejected", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, take_profit: 0.01 }))
      .toContain("take_profit 0.01 looks like a placeholder");
  });

  test("degenerate stop_loss 0.01: rejected", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, stop_loss: 0.01 }))
      .toContain("stop_loss 0.01 looks like a placeholder");
  });

  test("degenerate trail_price 0.01: rejected", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, trail_price: 0.01 }))
      .toContain("trail_price 0.01 looks like a placeholder");
  });

  test("degenerate trail_percent 0.01: rejected", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, trail_percent: 0.01 }))
      .toContain("trail_percent 0.01 looks like a placeholder");
  });

  test("degenerate notional 0.01: rejected", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", notional: 0.01, order_type: "market" }))
      .toContain("notional 0.01 looks like a placeholder");
  });

  test("degenerate limit_price 0.01: rejected", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10, order_type: "limit", limit_price: 0.01 }))
      .toContain("limit_price 0.01 looks like a placeholder");
  });

  test("undefined optional fields: no error", () => {
    expect(validatePlaceOrderArgs({ symbol: "AAPL", side: "buy", qty: 10 })).toBeNull();
  });
});

describe("validateReplaceOrderArgs", () => {
  test("valid replace with qty only: no error", () => {
    expect(validateReplaceOrderArgs({ order_id: "abc", qty: 5 })).toBeNull();
  });

  test("valid replace with limit_price only: no error", () => {
    expect(validateReplaceOrderArgs({ order_id: "abc", limit_price: 150 })).toBeNull();
  });

  test("degenerate qty 0.01: rejected", () => {
    expect(validateReplaceOrderArgs({ order_id: "abc", qty: 0.01 }))
      .toContain("qty 0.01 looks like a placeholder");
  });

  test("degenerate limit_price 0.01: rejected", () => {
    expect(validateReplaceOrderArgs({ order_id: "abc", limit_price: 0.01 }))
      .toContain("limit_price 0.01 looks like a placeholder");
  });

  test("degenerate stop_price 0.01: rejected", () => {
    expect(validateReplaceOrderArgs({ order_id: "abc", stop_price: 0.01 }))
      .toContain("stop_price 0.01 looks like a placeholder");
  });

  test("degenerate trail 0.01: rejected", () => {
    expect(validateReplaceOrderArgs({ order_id: "abc", trail: 0.01 }))
      .toContain("trail 0.01 looks like a placeholder");
  });
});

// L1 zod .refine() tests live in steer-handler.test.ts (handleStructured
// integration) and are also exercised by the Python contract/steering tests.
// Direct unit test of placeOrderValidator requires zod import from the test
// context, which bun can't resolve in this monorepo setup. The .refine() logic
// is verified via:
//   - steer-handler.test.ts: place_order with degenerate fields rejected
//   - test_steering_commands.py: place_order valid/invalid arg tests
//   - contract.test.ts: cross-language schema sync
