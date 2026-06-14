"use client";

import { useSnapshot } from "@/lib/use-snapshot";
import { fmtMoney, fmtQty, fmtTime } from "@/lib/format";

/** Most recent executions (newest last in the snapshot; shown newest-first). */
export function RecentFills() {
  const { snapshot, isLoading } = useSnapshot();
  const fills = [...(snapshot?.recent_fills ?? [])].reverse();

  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">Recent Fills</h2>
      {fills.length === 0 ? (
        <div data-testid="recent-fills-empty" className="py-6 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "체결 내역 없음"}
        </div>
      ) : (
        <ul data-testid="recent-fills" className="space-y-1 text-sm">
          {fills.map((f, i) => (
            <li
              key={`${f.ts}-${f.symbol}-${i}`}
              data-testid={`recent-fill-${i}`}
              className="flex items-center justify-between border-b border-edge/40 py-1 last:border-0"
            >
              <span className="flex items-center gap-2">
                <span className="text-ink-dim">{fmtTime(f.ts)}</span>
                <span
                  className={`uppercase ${f.side === "buy" ? "text-up" : f.side === "sell" ? "text-down" : "text-ink-dim"}`}
                >
                  {f.side ?? "—"}
                </span>
                <span className="font-medium text-ink">{f.symbol}</span>
              </span>
              <span className="text-ink-dim">
                {fmtQty(f.qty)} @ <span className="text-ink">{fmtMoney(f.price)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
