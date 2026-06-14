"use client";

import { trpc } from "@/lib/trpc";
import { fmtMoney, fmtQty, fmtSignedMoney, pnlClass } from "@/lib/format";
import type { Trade } from "@/server/schemas";

/** Closed round-trip trades (trades.jsonl) — the realized-PnL history. */
export function TradesTable() {
  const { data, isLoading } = trpc.portfolio.trades.useQuery({ limit: 50 });
  // Re-assert wire shape (tRPC Serialize flattening), newest first.
  const trades = [...((data as Trade[] | undefined) ?? [])].reverse();

  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">
        Closed Trades {trades.length > 0 && <span className="text-ink-dim">({trades.length})</span>}
      </h2>
      {trades.length === 0 ? (
        <div data-testid="trades-empty" className="py-6 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "청산된 트레이드 없음"}
        </div>
      ) : (
        <table data-testid="trades-table" className="w-full text-sm">
          <thead>
            <tr className="border-b border-edge text-left text-xs uppercase tracking-wide text-ink-dim">
              <th className="pb-2 font-medium">Symbol</th>
              <th className="pb-2 text-right font-medium">Qty</th>
              <th className="pb-2 text-right font-medium">Entry</th>
              <th className="pb-2 text-right font-medium">Exit</th>
              <th className="pb-2 text-right font-medium">P&L</th>
              <th className="pb-2 text-right font-medium">Return</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr
                key={`${t.symbol}-${t.closed_at}-${i}`}
                data-testid={`trade-row-${i}`}
                className="border-b border-edge/50 last:border-0"
              >
                <td className="py-2 font-medium text-ink">{t.symbol}</td>
                <td className="py-2 text-right text-ink">{fmtQty(t.qty)}</td>
                <td className="py-2 text-right text-ink-dim">{fmtMoney(t.entry_price)}</td>
                <td className="py-2 text-right text-ink-dim">{fmtMoney(t.exit_price)}</td>
                <td className={`py-2 text-right ${pnlClass(t.realized_pnl)}`}>
                  {fmtSignedMoney(t.realized_pnl)}
                </td>
                <td className={`py-2 text-right ${pnlClass(t.return_pct)}`}>
                  {t.return_pct != null ? `${t.return_pct > 0 ? "+" : ""}${t.return_pct.toFixed(2)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
