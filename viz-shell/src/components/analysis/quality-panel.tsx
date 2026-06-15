"use client";

import { trpc } from "@/lib/trpc";
import { fmtPct } from "@/lib/format";
import type { Quality } from "@/server/schemas";

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-1 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-ink-dim">{label}</div>
      <div className="mt-1 text-lg font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-dim">{sub}</div>}
    </div>
  );
}

function num(v: number | undefined, digits = 2): string {
  return v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);
}

/** Latest decision-quality metrics (workspace/quality/<date>.json, F24). */
export function QualityPanel() {
  const { data, isLoading } = trpc.portfolio.quality.useQuery();
  const payload = data as { date: string; metrics: Quality } | null | undefined;

  if (!isLoading && (payload === null || payload === undefined)) {
    return (
      <div data-testid="quality-empty" className="rounded-lg border border-edge bg-surface-1 p-4 text-sm text-ink-dim">
        품질 지표 없음 — 아직 산출 전?
      </div>
    );
  }
  const m = payload?.metrics;
  const dhr = m?.direction_hit_rate;
  const tgt = m?.target_quality;
  const stop = m?.stop_quality;

  return (
    <div data-testid="quality-panel" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Decision Quality</h2>
        {payload?.date && <span className="text-xs text-ink-dim">as of {payload.date}</span>}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric
          label="Direction hit"
          value={fmtPct(dhr?.rate)}
          sub={dhr ? `${dhr.hits ?? 0}/${dhr.total ?? 0}` : undefined}
        />
        <Metric
          label="Target reach"
          value={fmtPct(tgt?.reach_rate)}
          sub={tgt ? `${tgt.reached_count ?? 0}/${tgt.total ?? 0}` : undefined}
        />
        <Metric label="Realized RR" value={num(m?.realized_rr?.mean)} sub={`n=${m?.realized_rr?.count ?? 0}`} />
        <Metric label="Exit timing" value={num(m?.exit_timing?.mean, 3)} sub={`n=${m?.exit_timing?.count ?? 0}`} />
        <Metric
          label="Stop quality"
          value={stop ? `${stop.appropriate ?? 0} ok` : "—"}
          sub={stop ? `${stop.noise_hit ?? 0} noise / ${stop.total ?? 0}` : undefined}
        />
        <Metric label="Excess SPY" value={num(m?.benchmark_excess_spy?.mean, 3)} />
        <Metric label="Excess QQQ" value={num(m?.benchmark_excess_qqq?.mean, 3)} />
        <Metric label="Outcomes" value={String(m?.total_outcomes ?? "—")} />
      </div>
    </div>
  );
}
