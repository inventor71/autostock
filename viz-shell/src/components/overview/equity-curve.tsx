"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { trpc } from "@/lib/trpc";
import { fmtMoney } from "@/lib/format";
import {
  CHART_ACCENT,
  CHART_AXIS_STROKE,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_STYLE,
} from "@/lib/chart-theme";

const WINDOWS = [7, 30, 90] as const;

export function EquityCurve() {
  const [sinceDays, setSinceDays] = useState<(typeof WINDOWS)[number]>(30);
  const { data: records, isLoading } = trpc.portfolio.equity.useQuery({ sinceDays });

  const points = (records ?? []).map((r) => ({
    date: r.ts.slice(0, 10),
    equity: r.equity,
  }));

  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Equity Curve</h2>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              data-testid={`equity-window-${w}`}
              onClick={() => setSinceDays(w)}
              className={`rounded px-2 py-0.5 text-xs ${
                sinceDays === w
                  ? "bg-accent/20 text-accent"
                  : "text-ink-dim hover:bg-surface-2"
              }`}
            >
              {w}d
            </button>
          ))}
        </div>
      </div>
      {points.length === 0 ? (
        <div data-testid="equity-curve-empty" className="py-10 text-center text-sm text-ink-dim">
          {isLoading ? "로딩 중…" : "equity 기록 없음 — 데몬 미가동?"}
        </div>
      ) : (
        <div data-testid="equity-curve-chart" className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
              <CartesianGrid stroke={CHART_GRID_STROKE} strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke={CHART_AXIS_STROKE} fontSize={11} tickLine={false} />
              <YAxis
                stroke={CHART_AXIS_STROKE}
                fontSize={11}
                tickLine={false}
                domain={["auto", "auto"]}
                width={70}
                tickFormatter={(v: number) => fmtMoney(v)}
              />
              <Tooltip
                contentStyle={CHART_TOOLTIP_STYLE}
                formatter={(v) => [fmtMoney(Number(v)), "equity"]}
              />
              <Line
                type="monotone"
                dataKey="equity"
                stroke={CHART_ACCENT}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
