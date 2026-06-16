"use client";

import type { ComponentType } from "react";

import { OverviewTab } from "@/components/overview/overview-tab";
import { AnalysisTab } from "@/components/analysis/analysis-tab";
import { ResearchTab } from "@/components/research/research-tab";

/**
 * Built-in (seed) tabs — fixed, cannot be hidden, always present alongside any
 * chat-generated views. Add a tab by appending one entry here.
 */
export type SeedTab = { id: string; label: string; Component: ComponentType };

export const SEED_TABS: SeedTab[] = [
  { id: "overview", label: "Overview", Component: OverviewTab },
  { id: "analysis", label: "Analysis", Component: AnalysisTab },
  { id: "research", label: "Research", Component: ResearchTab },
];

/** Default/fallback tab when the active selection is gone (e.g. deleted view). */
export const OVERVIEW_TAB = SEED_TABS[0].id;

export const SEED_TAB_IDS = new Set(SEED_TABS.map((t) => t.id));
export const isSeedTab = (id: string): boolean => SEED_TAB_IDS.has(id);
