"use client";

import { trpc } from "@/lib/trpc";
import type { Scan, Verdict } from "@/server/schemas";

type ScreeningData = { date: string; dates: string[]; scan: Scan | null; verdicts: Verdict[] } | null;

function verdictClass(v: string): string {
  const x = v.toLowerCase();
  if (x === "passed" || x === "pass") return "text-up";
  if (x === "rejected" || x === "reject" || x === "failed") return "text-down";
  return "text-ink-dim";
}

/** Screening funnel (F72): scan size → per-symbol verdicts with reasons. */
export function ScreeningFunnel() {
  const { data, isLoading } = trpc.portfolio.screening.useQuery();
  const payload = data as ScreeningData | undefined;

  if (!isLoading && (payload === null || payload === undefined)) {
    return (
      <div data-testid="screening-empty" className="rounded-lg border border-edge bg-surface-1 p-4 text-sm text-ink-dim">
        스크리닝 로그 없음 — 아직 스캔 전?
      </div>
    );
  }

  const verdicts = payload?.verdicts ?? [];
  const scanCount = payload?.scan?.count ?? payload?.scan?.rows.length ?? 0;

  return (
    <div data-testid="screening-funnel" className="rounded-lg border border-edge bg-surface-1 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">
          Screening Funnel <span className="text-ink-dim">— {scanCount} scanned → {verdicts.length} verdicts</span>
        </h2>
        {payload?.date && <span className="text-xs text-ink-dim">{payload.date}</span>}
      </div>
      {verdicts.length === 0 ? (
        <div className="py-6 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "verdict 없음"}
        </div>
      ) : (
        <ul data-testid="screening-verdicts" className="space-y-1.5 text-sm">
          {verdicts.map((v, i) => (
            <li key={`${v.symbol}-${i}`} data-testid={`verdict-${i}`} className="border-b border-edge/40 pb-1.5 last:border-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-ink">{v.symbol}</span>
                <span className={`text-xs font-semibold uppercase ${verdictClass(v.verdict)}`}>{v.verdict}</span>
              </div>
              {v.reason && <p className="mt-0.5 text-xs leading-relaxed text-ink-dim">{v.reason}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
