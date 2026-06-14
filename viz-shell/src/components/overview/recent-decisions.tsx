"use client";

import { useState } from "react";

import { trpc } from "@/lib/trpc";
import { fmtMoney, fmtPct, fmtTime } from "@/lib/format";
import type { Decision } from "@/server/schemas";

/**
 * Recent agent decisions with the reasoning narrative (decisions.jsonl). The
 * `reason` is the most information-dense field the agent produces — collapsed by
 * default, click a row to read why it decided what it did.
 */
function actionClass(action: string): string {
  const a = action.toUpperCase();
  if (a === "BUY") return "text-up";
  if (a === "SELL" || a === "SHORT") return "text-down";
  return "text-ink-dim"; // HOLD / ADJUST_STOP / ...
}

export function RecentDecisions() {
  const { data, isLoading } = trpc.portfolio.decisions.useQuery({ limit: 20 });
  const [open, setOpen] = useState<number | null>(null);

  // tRPC's Serialize flattens the loose zod object — re-assert the wire shape
  // (same pattern as useSnapshot). Newest first (file is chronological append).
  const decisions = [...((data as Decision[] | undefined) ?? [])].reverse();

  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">Recent Decisions</h2>
      {decisions.length === 0 ? (
        <div data-testid="recent-decisions-empty" className="py-6 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "결정 내역 없음 — 데몬 미가동?"}
        </div>
      ) : (
        <ul data-testid="recent-decisions" className="space-y-1 text-sm">
          {decisions.map((d, i) => {
            const isOpen = open === i;
            return (
              <li
                key={`${d.ts}-${d.symbol}-${i}`}
                data-testid={`decision-${i}`}
                className="border-b border-edge/40 py-1.5 last:border-0"
              >
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : i)}
                  className="flex w-full items-center justify-between gap-2 text-left"
                  title={d.reason ? "클릭하면 근거를 봅니다" : undefined}
                >
                  <span className="flex items-center gap-2">
                    <span className="text-ink-dim">{fmtTime(d.ts)}</span>
                    <span className={`font-semibold uppercase ${actionClass(d.action)}`}>
                      {d.action}
                    </span>
                    <span className="font-medium text-ink">{d.symbol}</span>
                    {d.confidence != null && (
                      <span className="text-ink-dim">conf {fmtPct(d.confidence)}</span>
                    )}
                  </span>
                  <span className="flex items-center gap-2 text-xs text-ink-dim">
                    {d.stop != null && <span>stop {fmtMoney(d.stop)}</span>}
                    {d.target != null && <span>tgt {fmtMoney(d.target)}</span>}
                    {d.reason && <span>{isOpen ? "▴" : "▾"}</span>}
                  </span>
                </button>
                {isOpen && d.reason && (
                  <p
                    data-testid={`decision-reason-${i}`}
                    className="mt-1.5 whitespace-pre-wrap rounded bg-surface-0 px-2 py-1.5 text-xs leading-relaxed text-ink-dim"
                  >
                    {d.reason}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
