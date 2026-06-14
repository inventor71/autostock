"use client";

import { useSnapshot } from "@/lib/use-snapshot";

/**
 * Run-state strip (BR-8 fail-honest): paused / entries-halted / ET date.
 * Quiet when nominal; amber when the daemon is paused or halting entries so the
 * operator notices at a glance.
 */
export function RunStateBadge() {
  const { snapshot } = useSnapshot();
  const rs = snapshot?.run_state;
  if (!rs) return null;

  const paused = rs.paused === true;
  const halted = rs.entries_halted === true;

  return (
    <div
      data-testid="run-state-badge"
      className="flex items-center gap-3 text-xs text-ink-dim"
    >
      {rs.et_date && (
        <span data-testid="run-state-date">
          ET <span className="text-ink">{rs.et_date}</span>
        </span>
      )}
      <span
        data-testid="run-state-paused"
        className={paused ? "rounded bg-warn/15 px-1.5 py-0.5 text-warn" : "text-up"}
      >
        {paused ? "⏸ PAUSED" : "● running"}
      </span>
      {halted && (
        <span
          data-testid="run-state-halted"
          className="rounded bg-warn/15 px-1.5 py-0.5 text-warn"
        >
          entries halted
        </span>
      )}
    </div>
  );
}
