"use client";

import { trpc } from "@/lib/trpc";
import type { Health } from "@/server/schemas";

function statusClass(status: string | undefined): string {
  switch ((status ?? "").toUpperCase()) {
    case "OK":
      return "text-up";
    case "WARNING":
      return "text-warn";
    case "ERROR":
      return "text-down";
    default:
      return "text-ink-dim";
  }
}

/** System health verdict (steering/health.json, F63/F69). */
export function HealthPanel() {
  const { data, isLoading } = trpc.portfolio.health.useQuery();
  const health = data as Health | null | undefined;

  if (!isLoading && (health === null || health === undefined)) {
    return (
      <div data-testid="health-empty" className="rounded-lg border border-edge bg-surface-1 p-4 text-sm text-ink-dim">
        health 없음 — 데몬 미가동 또는 steering off?
      </div>
    );
  }

  const dims = Object.entries(health?.dimensions ?? {});

  return (
    <div data-testid="health-panel" className="rounded-lg border border-edge bg-surface-1 p-4">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-ink">System Health</h2>
        <span className={`text-sm font-semibold ${statusClass(health?.overall)}`}>
          {health?.overall ?? "—"}
        </span>
      </div>
      {dims.length === 0 ? (
        <div className="text-sm text-ink-dim">{isLoading ? "로딩 중…" : "차원 데이터 없음"}</div>
      ) : (
        <ul className="space-y-2 text-sm">
          {dims.map(([name, dim]) => {
            const bad = (dim.checks ?? []).filter(
              (c) => c.status !== "OK" && c.status !== "SKIPPED",
            );
            return (
              <li key={name} data-testid={`health-dim-${name}`} className="border-b border-edge/40 pb-2 last:border-0">
                <div className="flex items-center justify-between">
                  <span className="text-ink">{name}</span>
                  <span className={statusClass(dim.status)}>{dim.status}</span>
                </div>
                {bad.map((c, i) => (
                  <div key={i} className="mt-0.5 flex justify-between gap-2 text-xs">
                    <span className="text-ink-dim">{c.name}</span>
                    <span className={statusClass(c.status)} title={c.detail ?? c.error ?? undefined}>
                      {c.detail ?? c.status}
                    </span>
                  </div>
                ))}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
