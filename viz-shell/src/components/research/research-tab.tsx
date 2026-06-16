"use client";

import { ScreeningFunnel } from "@/components/research/screening-funnel";
import { SentimentPanel } from "@/components/research/sentiment-panel";
import { MarkdownDoc } from "@/components/analysis/markdown-doc";

/**
 * Research seed tab (Tier 3): the discovery funnel — what the agent scanned,
 * passed/rejected, retail sentiment, surge history, daily report, and lessons.
 * Dated artifacts default to the latest; a chat-generated view can pull any date.
 */
export function ResearchTab() {
  return (
    <div data-testid="research-tab" className="flex flex-col gap-4 p-4">
      <ScreeningFunnel />
      <SentimentPanel />
      <MarkdownDoc which="surge" title="Surge / Dive" />
      <MarkdownDoc which="daily" title="Daily Report" />
      <MarkdownDoc which="lessons" title="Lessons" />
    </div>
  );
}
