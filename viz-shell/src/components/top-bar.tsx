"use client";

import { useEffect, useRef, useState } from "react";

import type { GeneratedView } from "@/components/view-host";

export function TopBar({
  views,
  hidden,
  onRestore,
  chatOpen,
  onOpenChat,
}: {
  views: GeneratedView[];
  hidden: string[];
  onRestore: (fileName: string) => void;
  chatOpen: boolean;
  onOpenChat: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Only list hidden files that still exist (deleted files are harmless orphans).
  const hiddenViews = views.filter((v) => hidden.includes(v.fileName));

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menuOpen]);

  return (
    <header className="flex items-center justify-between border-b border-edge bg-surface-1 px-4 py-2">
      <h1 className="text-sm font-semibold tracking-wide text-ink">
        AUTOSTOCK <span className="text-accent">viz-shell</span>
      </h1>
      <div className="flex items-center gap-2">
        {hiddenViews.length > 0 && (
          <div ref={menuRef} className="relative">
            <button
              type="button"
              data-testid="hidden-views-button"
              onClick={() => setMenuOpen((v) => !v)}
              className="rounded px-2 py-1 text-xs text-ink-dim hover:bg-surface-2 hover:text-ink"
            >
              숨긴 뷰 ({hiddenViews.length}) ▾
            </button>
            {menuOpen && (
              <div
                data-testid="hidden-views-menu"
                className="absolute right-0 top-full z-30 mt-1 min-w-44 rounded-md border border-edge bg-surface-2 py-1 shadow-xl"
              >
                {hiddenViews.map((v) => (
                  <button
                    key={v.fileName}
                    type="button"
                    data-testid={`hidden-views-restore-${v.fileName}`}
                    onClick={() => {
                      onRestore(v.fileName);
                      setMenuOpen(false);
                    }}
                    className="block w-full px-3 py-1.5 text-left text-xs text-ink hover:bg-surface-1"
                  >
                    {v.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {!chatOpen && (
          <button
            type="button"
            data-testid="chat-expand-button"
            onClick={onOpenChat}
            className="rounded px-2 py-1 text-xs text-ink-dim hover:bg-surface-2 hover:text-ink"
          >
            ⇤ 채팅
          </button>
        )}
      </div>
    </header>
  );
}
