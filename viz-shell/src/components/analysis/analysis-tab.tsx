"use client";

import { QualityPanel } from "@/components/analysis/quality-panel";
import { HealthPanel } from "@/components/analysis/health-panel";
import { MarkdownDoc } from "@/components/analysis/markdown-doc";

/**
 * Analysis seed tab (Tier 2): decision-quality metrics, system health, and the
 * large research docs (watchlist/regime). Kept off Overview to avoid crowding.
 */
export function AnalysisTab() {
  return (
    <div data-testid="analysis-tab" className="flex flex-col gap-4 p-4">
      <QualityPanel />
      <HealthPanel />
      <MarkdownDoc which="watchlist" title="Watchlist" />
      <MarkdownDoc which="regime" title="Market Regime" />
    </div>
  );
}
