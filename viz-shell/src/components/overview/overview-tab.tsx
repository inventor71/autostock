"use client";

import { AccountCards } from "@/components/overview/account-cards";
import { RunStateBadge } from "@/components/overview/run-state-badge";
import { RoundTripCard } from "@/components/overview/round-trip-card";
import { EquityCurve } from "@/components/overview/equity-curve";
import { PositionsTable } from "@/components/overview/positions-table";
import { OpenOrdersTable } from "@/components/overview/open-orders-table";
import { RecentDecisions } from "@/components/overview/recent-decisions";
import { RecentFills } from "@/components/overview/recent-fills";
import { TradesTable } from "@/components/overview/trades-table";

/**
 * Seed view (fixed tab, cannot be hidden). Each widget renders its own honest
 * placeholder when daemon artifacts are absent — never a blank page (BR-8).
 * All data comes from the single snapshot query (useSnapshot, react-query deduped).
 */
export function OverviewTab() {
  return (
    <div data-testid="overview-tab" className="flex flex-col gap-4 p-4">
      <RunStateBadge />
      <AccountCards />
      <RoundTripCard />
      <EquityCurve />
      <PositionsTable />
      <OpenOrdersTable />
      <RecentDecisions />
      <TradesTable />
      <RecentFills />
    </div>
  );
}
