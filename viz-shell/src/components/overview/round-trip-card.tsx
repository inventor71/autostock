"use client";

import { useSnapshot } from "@/lib/use-snapshot";
import { fmtSignedMoney, fmtPct, pnlClass } from "@/lib/format";

/**
 * Closed round-trip stats (realized side, complements Open P&L which is unrealized).
 * win_rate is null until the first round trip closes — rendered honestly as "—".
 */
export function RoundTripCard() {
  const { snapshot } = useSnapshot();
  const rt = snapshot?.round_trip;
  if (!rt) return null;

  const closed = rt.closed_count ?? 0;

  return (
    <div
      data-testid="round-trip-card"
      className="grid grid-cols-3 gap-3 rounded-lg border border-edge bg-surface-1 px-4 py-3"
    >
      <div>
        <div className="text-xs uppercase tracking-wide text-ink-dim">Closed</div>
        <div className="mt-1 text-lg font-semibold text-ink">{closed}</div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-ink-dim">Win rate</div>
        <div className="mt-1 text-lg font-semibold text-ink">{fmtPct(rt.win_rate)}</div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-ink-dim">Realized P&L</div>
        <div className={`mt-1 text-lg font-semibold ${pnlClass(rt.realized_pnl)}`}>
          {fmtSignedMoney(rt.realized_pnl)}
        </div>
      </div>
    </div>
  );
}
