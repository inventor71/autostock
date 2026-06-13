import { describe, expect, it } from "vitest";

import { fmtMoney, fmtQty, fmtSignedMoney, pnlClass } from "@/lib/format";

describe("format helpers (fail-honest: null → '—')", () => {
  it("fmtMoney", () => {
    expect(fmtMoney(99614.5)).toBe("$99,614.50");
    expect(fmtMoney(null)).toBe("—");
    expect(fmtMoney(undefined)).toBe("—");
    expect(fmtMoney(NaN)).toBe("—");
  });

  it("fmtSignedMoney adds + for gains only", () => {
    expect(fmtSignedMoney(136.61)).toBe("+$136.61");
    expect(fmtSignedMoney(-12)).toBe("-$12.00");
    expect(fmtSignedMoney(undefined)).toBe("—");
  });

  it("fmtQty trims integers, keeps fractions", () => {
    expect(fmtQty(19)).toBe("19");
    expect(fmtQty(1.5)).toBe("1.50");
    expect(fmtQty(null)).toBe("—");
  });

  it("pnlClass maps sign to color token", () => {
    expect(pnlClass(5)).toBe("text-up");
    expect(pnlClass(-5)).toBe("text-down");
    expect(pnlClass(0)).toBe("text-ink-dim");
    expect(pnlClass(undefined)).toBe("text-ink-dim");
  });
});
