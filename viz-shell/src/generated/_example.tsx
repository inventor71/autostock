"use client";

/**
 * REFERENCE VIEW — the contract every generated view follows (BR-10/11).
 * Files starting with "_" are not shown as tabs.
 *
 * Rules:
 *  1. One view = one file in src/generated/, kebab-case name, .tsx.
 *  2. `export const meta = { title: "..." }` — the tab label.
 *  3. `export default` a React component.
 *  4. Data ONLY via tRPC hooks (`trpc.portfolio.*`) — no fetch/fs/imports of
 *     server code. Poll live data with `refetchInterval`.
 *  5. recharts for charts (use the shared constants from "@/lib/chart-theme");
 *     Tailwind utilities with the dark tokens (bg-surface-1, border-edge,
 *     text-ink, text-ink-dim, text-up, text-down, text-accent, text-warn).
 *  6. Render honest placeholders for missing data — never fabricate values.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { trpc } from "@/lib/trpc";
import {
  CHART_ACCENT,
  CHART_AXIS_STROKE,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
} from "@/lib/chart-theme";

export const meta = { title: "Example (reference)" };

export default function ExampleView() {
  const { data: snapshot } = trpc.portfolio.snapshot.useQuery(undefined, {
    refetchInterval: 5_000,
  });

  const rows = Object.entries(snapshot?.positions ?? {}).map(([symbol, p]) => ({
    symbol,
    pnl: p.unrealized_pnl ?? 0,
  }));

  if (rows.length === 0) {
    return (
      <div className="m-6 rounded-lg border border-edge bg-surface-1 p-6 text-sm text-ink-dim">
        포지션 없음 — 데이터가 생기면 자동 갱신됩니다.
      </div>
    );
  }

  return (
    <div className="m-6 rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">Unrealized P&L by Symbol</h2>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows}>
            <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" />
            <XAxis dataKey="symbol" stroke={CHART_AXIS_STROKE} fontSize={12} />
            <YAxis stroke={CHART_AXIS_STROKE} fontSize={12} />
            <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
            <Bar dataKey="pnl" fill={CHART_ACCENT} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
