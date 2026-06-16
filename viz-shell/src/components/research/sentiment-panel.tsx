"use client";

import { trpc } from "@/lib/trpc";
import type { Sentiment } from "@/server/schemas";

type SentimentData = { date: string; dates: string[]; rows: Sentiment[] } | null;

/** StockTwits retail sentiment (F77): per-symbol bull/bear, most-discussed first. */
export function SentimentPanel() {
  const { data, isLoading } = trpc.portfolio.sentiment.useQuery();
  const payload = data as SentimentData | undefined;

  if (!isLoading && (payload === null || payload === undefined)) {
    return (
      <div data-testid="sentiment-empty" className="rounded-lg border border-edge bg-surface-1 p-4 text-sm text-ink-dim">
        센티먼트 데이터 없음
      </div>
    );
  }

  // Latest row per symbol, ranked by total tagged volume.
  const bySymbol = new Map<string, Sentiment>();
  for (const r of payload?.rows ?? []) bySymbol.set(r.symbol, r);
  const rows = [...bySymbol.values()]
    .map((r) => ({ ...r, bull: r.bullish_n ?? 0, bear: r.bearish_n ?? 0 }))
    .sort((a, b) => b.bull + b.bear - (a.bull + a.bear))
    .slice(0, 20);

  return (
    <div data-testid="sentiment-panel" className="rounded-lg border border-edge bg-surface-1 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Retail Sentiment</h2>
        {payload?.date && <span className="text-xs text-ink-dim">{payload.date}</span>}
      </div>
      {rows.length === 0 ? (
        <div className="py-6 text-center text-sm text-ink-dim">{isLoading ? "로딩 중…" : "데이터 없음"}</div>
      ) : (
        <ul data-testid="sentiment-rows" className="space-y-1.5 text-sm">
          {rows.map((r) => {
            const total = r.bull + r.bear;
            const bullPct = total > 0 ? (r.bull / total) * 100 : 0;
            return (
              <li key={r.symbol} data-testid={`sentiment-${r.symbol}`} className="flex items-center gap-3">
                <span className="w-16 shrink-0 font-medium text-ink">{r.symbol}</span>
                <div className="flex h-2 flex-1 overflow-hidden rounded bg-surface-0">
                  <div className="bg-up/70" style={{ width: `${bullPct}%` }} />
                  <div className="bg-down/70" style={{ width: `${100 - bullPct}%` }} />
                </div>
                <span className="w-20 shrink-0 text-right text-xs text-ink-dim">
                  <span className="text-up">{r.bull}</span> / <span className="text-down">{r.bear}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
