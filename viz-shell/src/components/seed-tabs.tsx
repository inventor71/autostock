"use client";

import type { ComponentType } from "react";

import { OverviewTab } from "@/components/overview/overview-tab";
import { ExploreTab } from "@/components/explore/explore-tab";

/**
 * Built-in (seed) tabs — fixed, cannot be hidden. Kept deliberately small
 * (vibeOS-leaning): Overview holds the always-on, verified account/risk state;
 * Explore seeds on-demand generation (preset chips) + research-doc viewers.
 * Everything exploratory is reached via generated views, not hardcoded widgets.
 */
export type SeedTabProps = { onPreset?: (prompt: string) => void };
export type SeedTab = { id: string; label: string; Component: ComponentType<SeedTabProps> };

export const SEED_TABS: SeedTab[] = [
  { id: "overview", label: "Overview", Component: OverviewTab },
  { id: "explore", label: "Explore", Component: ExploreTab },
];

/** Default/fallback tab when the active selection is gone (e.g. deleted view). */
export const OVERVIEW_TAB = SEED_TABS[0].id;

export const SEED_TAB_IDS = new Set(SEED_TABS.map((t) => t.id));
export const isSeedTab = (id: string): boolean => SEED_TAB_IDS.has(id);
