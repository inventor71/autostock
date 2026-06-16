"use client";

import { trpc } from "@/lib/trpc";
import type { Health } from "@/server/schemas";
import { PresetGallery } from "@/components/explore/preset-gallery";
import { MarkdownDoc } from "@/components/explore/markdown-doc";

/**
 * Explore seed tab (vibeOS-leaning): exploratory data is reached via generated
 * views, not pre-drawn widgets. A preset-chip gallery seeds the generation, a
 * lightweight health badge stays (system status is always-on), and the large
 * research docs are kept as collapsible viewers (read, not generate).
 */
export function ExploreTab({ onPreset }: { onPreset?: (prompt: string) => void }) {
  const pick = (prompt: string) => onPreset?.(prompt);
  const { data } = trpc.portfolio.health.useQuery();
  const health = data as Health | null | undefined;
  const overall = health?.overall;

  return (
    <div data-testid="explore-tab" className="flex flex-col gap-4 p-4">
      {overall && (
        <div data-testid="health-badge" className="flex items-center gap-2 text-xs text-ink-dim">
          시스템 헬스:
          <span
            className={
              overall === "OK" ? "text-up" : overall === "WARNING" ? "text-warn" : "text-down"
            }
          >
            {overall}
          </span>
          <span className="text-ink-dim/70">— 상세는 “시스템 헬스” 칩으로 뷰 생성</span>
        </div>
      )}
      <PresetGallery onPick={pick} />
      <MarkdownDoc which="watchlist" title="Watchlist" />
      <MarkdownDoc which="regime" title="Market Regime" />
      <MarkdownDoc which="surge" title="Surge / Dive" />
      <MarkdownDoc which="daily" title="Daily Report" />
      <MarkdownDoc which="lessons" title="Lessons" />
    </div>
  );
}
