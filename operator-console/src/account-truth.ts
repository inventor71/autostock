// F94 — provider-aware account-truth reader for the console's MCP read tools.
//
// The console's "live" account tools (get_account_info / get_all_positions / get_open_position /
// get_orders / get_portfolio_history) historically hit the Alpaca trading API directly
// (alpaca-data.ts, via ALPACA_API_KEY). That is correct ONLY for an `alpaca` broker. For an
// `account_farm` instance the daemon trades a per-instance SUB-ACCOUNT that the Alpaca API can't
// see — so the Alpaca-direct read returns the shared Alpaca account (e.g. phantom RTX/TMO),
// disagreeing with the daemon (and the sidebar). This is the TS twin of the F92 Python bug.
//
// Fix: when AUTOSTOCK_BROKER_PROVIDER === "account_farm", source account truth from the daemon's
// published steering snapshot.json (the same account_farm truth the sidebar shows). Market-data
// tools are account-agnostic and stay Alpaca-direct (unchanged).
//
// Provider detection uses AUTOSTOCK_BROKER_PROVIDER (prod-run.sh injects it for account_farm
// instances). Empty/"alpaca" → unchanged Alpaca-direct behaviour.

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { AlpacaDataClient, formatResponse } from "./alpaca-data";

export interface AccountReader {
  getAccountInfo(): Promise<string>;
  getAllPositions(): Promise<string>;
  getOpenPosition(symbolOrAssetId: string): Promise<string>;
  getOrders(params?: Record<string, unknown>): Promise<string>;
  getPortfolioHistory(params?: Record<string, unknown>): Promise<string>;
}

export function isAccountFarm(provider: string | undefined): boolean {
  return (provider ?? "").toLowerCase() === "account_farm";
}

// Reads the daemon's published snapshot.json (account_farm truth) instead of the Alpaca API.
class SnapshotAccountReader implements AccountReader {
  constructor(private readonly steeringDir: string) {}

  private snap(): Record<string, any> | null {
    try {
      return JSON.parse(readFileSync(join(this.steeringDir, "snapshot.json"), "utf8"));
    } catch {
      return null; // not published yet / unreadable — handlers degrade with a clear note
    }
  }

  private asOf(s: Record<string, any> | null): string {
    return s?.published_at ? `(데몬 snapshot 기준 · as_of ${s.published_at})` : "(데몬 snapshot 기준)";
  }

  async getAccountInfo(): Promise<string> {
    const s = this.snap();
    if (!s) return "(no daemon snapshot — 데몬이 아직 발행 전이거나 STEERING_DIR 미설정)";
    const a = (s.account ?? {}) as Record<string, unknown>;
    return formatResponse(
      {
        source: "daemon snapshot (account_farm)",
        as_of: s.published_at ?? null,
        equity: a.equity ?? null,
        cash: a.cash ?? null,
        invested: a.invested ?? null,
        open_pnl: a.open_pnl ?? null,
        position_count: a.position_count ?? null,
      },
      "getAccountInfo",
    );
  }

  async getAllPositions(): Promise<string> {
    const s = this.snap();
    if (!s) return "(no daemon snapshot)";
    const pos = (s.positions ?? {}) as Record<string, any>;
    const rows = Object.entries(pos).map(([symbol, p]) => ({
      symbol,
      qty: p.qty,
      side: p.side,
      avg_entry_price: p.avg_entry_price,
      current_price: p.current_price,
      market_value: p.market_value,
      unrealized_pnl: p.unrealized_pnl,
    }));
    if (rows.length === 0) return `(보유 포지션 없음) ${this.asOf(s)}`;
    return `${formatResponse(rows, "getAllPositions")}\n\n${this.asOf(s)}`;
  }

  async getOpenPosition(symbolOrAssetId: string): Promise<string> {
    const s = this.snap();
    if (!s) return "(no daemon snapshot)";
    const sym = symbolOrAssetId.toUpperCase();
    const p = ((s.positions ?? {}) as Record<string, any>)[sym];
    if (!p) return `(${sym} 보유 없음) ${this.asOf(s)}`;
    return `${formatResponse({ symbol: sym, ...p }, "getOpenPosition")}\n\n${this.asOf(s)}`;
  }

  async getOrders(): Promise<string> {
    const s = this.snap();
    if (!s) return "(no daemon snapshot)";
    const oo = (s.open_orders ?? []) as unknown[];
    const note =
      "account_farm: 데몬 snapshot의 미체결(open) 주문만 표시 — 체결/취소 히스토리는 미지원" +
      "(사이드바·데몬 로그 참조).";
    if (oo.length === 0) return `(미체결 주문 없음)\n${note} ${this.asOf(s)}`;
    return `${formatResponse(oo, "getOrders")}\n\n${note} ${this.asOf(s)}`;
  }

  async getPortfolioHistory(): Promise<string> {
    const s = this.snap();
    return (
      "account_farm: 포트폴리오 히스토리는 데몬 snapshot에 없음 — 현재 equity는 get_account_info, " +
      `추이는 콘솔 사이드바/데몬 equity 로그를 참조하세요. ${s ? this.asOf(s) : ""}`.trim()
    );
  }
}

// Delegates to the Alpaca trading API (unchanged behaviour for `alpaca` brokers).
class AlpacaAccountReader implements AccountReader {
  constructor(private readonly client: AlpacaDataClient) {}
  getAccountInfo() {
    return this.client.getAccountInfo();
  }
  getAllPositions() {
    return this.client.getAllPositions();
  }
  getOpenPosition(symbolOrAssetId: string) {
    return this.client.getOpenPosition(symbolOrAssetId);
  }
  getOrders(params?: Record<string, unknown>) {
    return this.client.getOrders(params as never);
  }
  getPortfolioHistory(params?: Record<string, unknown>) {
    return this.client.getPortfolioHistory(params as never);
  }
}

export function createAccountReader(opts: {
  provider: string | undefined;
  steeringDir: string;
  alpaca: AlpacaDataClient;
}): AccountReader {
  return isAccountFarm(opts.provider)
    ? new SnapshotAccountReader(opts.steeringDir)
    : new AlpacaAccountReader(opts.alpaca);
}
