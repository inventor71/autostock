// F94 — provider-aware account reader. account_farm must read the daemon snapshot (its real
// sub-account), NOT the Alpaca API (which would return the shared Alpaca account / phantom holdings).

import { test, expect } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// alpaca-data.ts fail-fasts at import if ALPACA keys are absent — set dummies BEFORE importing
// (account-truth imports alpaca-data). Dynamic import so the env is in place first.
process.env.ALPACA_API_KEY = "test-key";
process.env.ALPACA_API_SECRET = "test-secret";
const { createAccountReader, isAccountFarm } = await import("../src/account-truth");

function steeringWith(snapshot: unknown): string {
  const dir = mkdtempSync(join(tmpdir(), "f94-steer-"));
  writeFileSync(join(dir, "snapshot.json"), JSON.stringify(snapshot));
  return dir;
}

const SNAP = {
  published_at: "2026-06-29T00:00:00+09:00",
  account: { equity: 79651.73, cash: 78256.29, invested: 1395.44, open_pnl: 25.0, position_count: 1 },
  positions: { HD: { qty: 4, side: "long", avg_entry_price: 342.61, current_price: 348.86, market_value: 1395.44, unrealized_pnl: 25.0 } },
  open_orders: [{ symbol: "HD", order_id: "abc", side: "sell", order_type: "limit", limit_price: 370, stop_price: null }],
};

test("isAccountFarm detects provider (case-insensitive)", () => {
  expect(isAccountFarm("account_farm")).toBe(true);
  expect(isAccountFarm("ACCOUNT_FARM")).toBe(true);
  expect(isAccountFarm("alpaca")).toBe(false);
  expect(isAccountFarm("")).toBe(false);
  expect(isAccountFarm(undefined)).toBe(false);
});

test("account_farm reads positions/account from daemon snapshot (its sub-account)", async () => {
  const steeringDir = steeringWith(SNAP);
  const r = createAccountReader({ provider: "account_farm", steeringDir, alpaca: null as never });

  const positions = await r.getAllPositions();
  expect(positions).toContain("HD");
  expect(positions).not.toContain("RTX"); // no phantom Alpaca holdings
  expect(positions).not.toContain("TMO");

  const acct = await r.getAccountInfo();
  expect(acct).toContain("79651.73");
  expect(acct).toContain("account_farm");

  const hd = await r.getOpenPosition("hd");
  expect(hd).toContain("HD");
  const rtx = await r.getOpenPosition("RTX");
  expect(rtx).toContain("보유 없음");
});

test("account_farm getOrders shows open-only with a note; portfolio_history degrades", async () => {
  const steeringDir = steeringWith(SNAP);
  const r = createAccountReader({ provider: "account_farm", steeringDir, alpaca: null as never });

  const orders = await r.getOrders();
  expect(orders).toContain("HD");
  expect(orders).toContain("미체결"); // open-only note

  const hist = await r.getPortfolioHistory();
  expect(hist).toContain("히스토리는 데몬 snapshot에 없음"); // graceful degrade
});

test("account_farm with no snapshot degrades cleanly (no throw)", async () => {
  const r = createAccountReader({ provider: "account_farm", steeringDir: "/nonexistent-f94", alpaca: null as never });
  const positions = await r.getAllPositions();
  expect(positions).toContain("no daemon snapshot");
});

test("alpaca/empty provider does NOT use the snapshot reader", () => {
  // For alpaca the reader must delegate to the Alpaca client (network) — we don't call it here,
  // just assert the factory did not pick the snapshot path (which would read the steering file).
  const steeringDir = steeringWith(SNAP);
  const alpacaReader = createAccountReader({ provider: "alpaca", steeringDir, alpaca: { tag: "ALPACA" } as never });
  const emptyReader = createAccountReader({ provider: undefined, steeringDir, alpaca: { tag: "ALPACA" } as never });
  // SnapshotAccountReader would never hold an `alpaca` client; the delegating reader does.
  expect((alpacaReader as unknown as { client?: unknown }).client).toBeDefined();
  expect((emptyReader as unknown as { client?: unknown }).client).toBeDefined();
});
