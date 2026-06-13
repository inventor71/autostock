"use client";

import type { GeneratedView } from "@/components/view-host";

export const OVERVIEW_TAB = "overview";

export function TabBar({
  views,
  active,
  onSelect,
  onHide,
}: {
  views: GeneratedView[]; // visible generated views only
  active: string;
  onSelect: (tab: string) => void;
  onHide: (fileName: string) => void;
}) {
  const tabClass = (isActive: boolean) =>
    `flex items-center gap-1 rounded-t-md border-b-2 px-3 py-1.5 text-sm ${
      isActive
        ? "border-accent text-ink"
        : "border-transparent text-ink-dim hover:bg-surface-2 hover:text-ink"
    }`;

  return (
    <nav
      data-testid="tab-bar"
      className="flex items-end gap-1 overflow-x-auto border-b border-edge bg-surface-1 px-2"
    >
      <button
        type="button"
        data-testid="tab-overview"
        onClick={() => onSelect(OVERVIEW_TAB)}
        className={tabClass(active === OVERVIEW_TAB)}
      >
        Overview
      </button>
      {views.map((v) => (
        <div key={v.fileName} className={tabClass(active === v.fileName)}>
          <button
            type="button"
            data-testid={`tab-${v.fileName}`}
            onClick={() => onSelect(v.fileName)}
            className="max-w-48 truncate"
            title={v.fileName}
          >
            {v.title}
          </button>
          <button
            type="button"
            data-testid={`tab-hide-${v.fileName}`}
            onClick={(e) => {
              e.stopPropagation();
              onHide(v.fileName);
            }}
            aria-label={`${v.title} 탭 숨기기 (파일은 유지)`}
            title="탭 숨기기 — 파일은 유지됩니다"
            className="rounded px-0.5 text-ink-dim hover:bg-surface-0 hover:text-ink"
          >
            ×
          </button>
        </div>
      ))}
    </nav>
  );
}
