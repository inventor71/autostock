"use client";

import { useState } from "react";

import { fmtMoney, fmtQty, fmtSignedMoney, pnlClass } from "@/lib/format";
import { useSnapshot } from "@/lib/use-snapshot";
import { ThesisDrawer } from "@/components/overview/thesis-drawer";

export function PositionsTable() {
  const { snapshot, isLoading } = useSnapshot();
  const [selected, setSelected] = useState<string | null>(null);

  const positions = Object.entries(snapshot?.positions ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );

  return (
    <div className="relative rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">Positions</h2>
      {positions.length === 0 ? (
        <div data-testid="positions-empty" className="py-6 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "보유 포지션 없음"}
        </div>
      ) : (
        <table data-testid="positions-table" className="w-full text-sm">
          <thead>
            <tr className="border-b border-edge text-left text-xs uppercase tracking-wide text-ink-dim">
              <th className="pb-2 font-medium">Symbol</th>
              <th className="pb-2 text-right font-medium">Qty</th>
              <th className="pb-2 text-right font-medium">Avg</th>
              <th className="pb-2 text-right font-medium">Price</th>
              <th className="pb-2 text-right font-medium">Value</th>
              <th className="pb-2 text-right font-medium">Unrealized</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(([symbol, pos]) => (
              <tr
                key={symbol}
                data-testid={`position-row-${symbol}`}
                onClick={() => setSelected(symbol)}
                title="클릭하면 thesis를 봅니다"
                className="cursor-pointer border-b border-edge/50 last:border-0 hover:bg-surface-2"
              >
                <td className="py-2 font-medium text-ink">
                  {symbol}
                  {pos.side === "short" && (
                    <span className="ml-1.5 rounded bg-down/15 px-1 text-xs text-down">short</span>
                  )}
                </td>
                <td className="py-2 text-right text-ink">{fmtQty(pos.qty)}</td>
                <td className="py-2 text-right text-ink-dim">{fmtMoney(pos.avg_entry_price)}</td>
                <td className="py-2 text-right text-ink">{fmtMoney(pos.current_price)}</td>
                <td className="py-2 text-right text-ink">{fmtMoney(pos.market_value)}</td>
                <td className={`py-2 text-right ${pnlClass(pos.unrealized_pnl)}`}>
                  {fmtSignedMoney(pos.unrealized_pnl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected !== null && (
        <ThesisDrawer symbol={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
