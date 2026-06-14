/** Display formatting for money/PnL — fail-honest: null/undefined render as "—". */

export function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export function fmtSignedMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${fmtMoney(v)}`;
}

export function fmtQty(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

/** Tailwind text color class for a PnL number. */
export function pnlClass(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v) || v === 0) return "text-ink-dim";
  return v > 0 ? "text-up" : "text-down";
}

/** ISO timestamp → local HH:MM, fail-honest "—". */
export function fmtTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const ms = Date.parse(ts);
  if (Number.isNaN(ms)) return "—";
  return new Date(ms).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Fraction (0..1) → percent string, fail-honest "—". */
export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(0)}%`;
}
