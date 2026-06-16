"use client";

/**
 * REFERENCE VIEW #2 — shows how to use the richer routers beyond `snapshot`
 * (see _example.tsx for the basic contract). Files starting with "_" are not
 * shown as tabs. This demonstrates: a jsonl-tail router (decisions), client-side
 * aggregation, and a recharts bar — the pattern an agent should copy when the
 * user asks for "decisions by X" / "turns cost over time" / etc.
 *
 * Dated routers (screening/sentiment/surge/daily) take an optional
 * {date:"YYYY-MM-DD"} and return a `dates` array for building a picker.
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

export const meta = { title: "Example: decisions by action" };

export default function ExampleResearchView() {
  const { data } = trpc.portfolio.decisions.useQuery({ limit: 200 }, { refetchInterval: 5_000 });

  const counts = new Map<string, number>();
  for (const d of data ?? []) counts.set(d.action, (counts.get(d.action) ?? 0) + 1);
  const rows = [...counts.entries()].map(([action, n]) => ({ action, n }));

  if (rows.length === 0) {
    return (
      <div className="m-6 rounded-lg border border-edge bg-surface-1 p-6 text-sm text-ink-dim">
        결정 내역 없음 — 데이터가 생기면 자동 갱신됩니다.
      </div>
    );
  }

  return (
    <div className="m-6 rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink">Decisions by Action</h2>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows}>
            <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" />
            <XAxis dataKey="action" stroke={CHART_AXIS_STROKE} fontSize={12} />
            <YAxis stroke={CHART_AXIS_STROKE} fontSize={12} allowDecimals={false} />
            <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
            <Bar dataKey="n" fill={CHART_ACCENT} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
