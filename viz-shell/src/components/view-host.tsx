"use client";

import { Suspense, lazy, type ComponentType, type LazyExoticComponent } from "react";

import { ViewErrorBoundary } from "@/components/error-boundary";
import { fileNameToTitle, isTabFile } from "@/lib/view-utils";

export type GeneratedView = {
  fileName: string;
  title: string;
  Component: LazyExoticComponent<ComponentType>;
};

type ViewModule = { default?: ComponentType; meta?: { title?: string } };
type WebpackContext = {
  keys(): string[];
  (id: string): unknown;
};

/**
 * Auto-registry (L4): webpack's require.context picks up new files under
 * src/generated/ in dev without any index edits — the agent writes ONE file
 * and HMR mounts it (BR-10). Module evaluation is deferred into React.lazy so
 * a broken view rejects inside its own ErrorBoundary instead of taking the
 * registry down.
 */
function loadContext(): WebpackContext | null {
  try {
    // Webpack statically analyzes this exact `require.context(...)` call.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (require as any).context("../generated", false, /\.tsx$/) as WebpackContext;
  } catch {
    return null; // non-webpack runtime (tests)
  }
}

// Stable view identities across re-renders (polling re-renders every 5s; a
// fresh lazy() each render would remount tabs). When HMR swaps the generated/
// context this whole module re-evaluates, so the cache resets naturally.
const viewCache = new Map<string, GeneratedView>();

export function discoverGeneratedViews(): GeneratedView[] {
  const ctx = loadContext();
  if (ctx === null) return [];
  return ctx
    .keys()
    .map((key) => ({ key, fileName: key.replace(/^\.\//, "") }))
    .filter(({ fileName }) => isTabFile(fileName))
    .sort((a, b) => a.fileName.localeCompare(b.fileName))
    .map(({ key, fileName }) => {
      const cached = viewCache.get(fileName);
      if (cached) return cached;

      const Component = lazy(async () => {
        // Evaluation happens here, per tab, inside the boundary.
        const mod = ctx(key) as ViewModule;
        if (typeof mod.default !== "function") {
          throw new Error(`${fileName} has no default-exported component`);
        }
        return { default: mod.default };
      });
      // Title needs the module too, but must not crash discovery — fall back
      // to the file name if evaluation throws (the tab itself will show the error).
      let title = fileNameToTitle(fileName);
      try {
        const metaTitle = (ctx(key) as ViewModule).meta?.title;
        if (typeof metaTitle === "string" && metaTitle.trim() !== "") title = metaTitle;
      } catch {
        // broken module — keep fallback title
      }
      const view: GeneratedView = { fileName, title, Component };
      viewCache.set(fileName, view);
      return view;
    });
}

export function GeneratedViewHost({ view }: { view: GeneratedView }) {
  const { Component } = view;
  return (
    <ViewErrorBoundary viewTitle={view.title}>
      <Suspense
        fallback={<div className="p-6 text-sm text-ink-dim">로딩 중… ({view.title})</div>}
      >
        <Component />
      </Suspense>
    </ViewErrorBoundary>
  );
}
