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
 *  5. recharts for charts; Tailwind utilities with the dark tokens
 *     (bg-surface-1, border-edge, text-ink, text-ink-dim, text-up, text-down,
 *     text-accent, text-warn).
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
            <CartesianGrid stroke="#232b3d" strokeDasharray="3 3" />
            <XAxis dataKey="symbol" stroke="#8b93a7" fontSize={12} />
            <YAxis stroke="#8b93a7" fontSize={12} />
            <Tooltip
              contentStyle={{
                background: "#11151f",
                border: "1px solid #232b3d",
                borderRadius: 8,
                color: "#d7dce6",
              }}
            />
            <Bar dataKey="pnl" fill="#7aa2f7" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
