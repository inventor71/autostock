"use client";

import { useSnapshot } from "@/lib/use-snapshot";
import { fmtMoney } from "@/lib/format";

/**
 * Resting orders (bracket/OCO legs). A trading dashboard that hides working
 * orders is the biggest gap in the seed view — this surfaces limit/stop legs
 * with their distance to the live price.
 */
export function OpenOrdersTable() {
  const { snapshot, isLoading } = useSnapshot();
  const orders = snapshot?.open_orders ?? [];

  const sideClass = (side: string | undefined) =>
    side === "buy" ? "text-up" : side === "sell" ? "text-down" : "text-ink-dim";

  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">
        Open Orders {orders.length > 0 && <span className="text-ink-dim">({orders.length})</span>}
      </h2>
      {orders.length === 0 ? (
        <div data-testid="open-orders-empty" className="py-6 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "미체결 주문 없음"}
        </div>
      ) : (
        <table data-testid="open-orders-table" className="w-full text-sm">
          <thead>
            <tr className="border-b border-edge text-left text-xs uppercase tracking-wide text-ink-dim">
              <th className="pb-2 font-medium">Symbol</th>
              <th className="pb-2 font-medium">Side</th>
              <th className="pb-2 font-medium">Type</th>
              <th className="pb-2 text-right font-medium">Limit</th>
              <th className="pb-2 text-right font-medium">Stop</th>
              <th className="pb-2 text-right font-medium">Last</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o, i) => (
              <tr
                key={o.order_id ?? `${o.symbol}-${i}`}
                data-testid={`open-order-row-${o.symbol}-${i}`}
                className="border-b border-edge/50 last:border-0"
              >
                <td className="py-2 font-medium text-ink">{o.symbol}</td>
                <td className={`py-2 uppercase ${sideClass(o.side)}`}>{o.side ?? "—"}</td>
                <td className="py-2 text-ink-dim">{o.order_type ?? "—"}</td>
                <td className="py-2 text-right text-ink">
                  {o.limit_price != null ? fmtMoney(o.limit_price) : "—"}
                </td>
                <td className="py-2 text-right text-ink">
                  {o.stop_price != null ? fmtMoney(o.stop_price) : "—"}
                </td>
                <td className="py-2 text-right text-ink-dim">{fmtMoney(o.current_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
