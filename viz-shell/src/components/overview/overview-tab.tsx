"use client";

import { AccountCards } from "@/components/overview/account-cards";
import { EquityCurve } from "@/components/overview/equity-curve";
import { PositionsTable } from "@/components/overview/positions-table";

/**
 * Seed view (fixed tab, cannot be hidden). Each widget renders its own honest
 * placeholder when daemon artifacts are absent — never a blank page (BR-8).
 */
export function OverviewTab() {
  return (
    <div data-testid="overview-tab" className="flex flex-col gap-4 p-4">
      <AccountCards />
      <EquityCurve />
      <PositionsTable />
    </div>
  );
}
