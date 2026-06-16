"use client";

import { useEffect, useRef, useState } from "react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { TabBar } from "@/components/tab-bar";
import { TopBar } from "@/components/top-bar";
import { GeneratedViewHost, discoverGeneratedViews } from "@/components/view-host";
import { OVERVIEW_TAB, SEED_TABS, isSeedTab } from "@/components/seed-tabs";
import {
  hideView,
  loadHiddenViews,
  restoreView,
  saveHiddenViews,
} from "@/lib/view-utils";

const CHAT_OPEN_KEY = "viz-shell.chat-open";

export default function DashboardPage() {
  const views = discoverGeneratedViews();
  const [active, setActive] = useState<string>(OVERVIEW_TAB);

  // Tab visibility lives in localStorage, decoupled from files (BR-13).
  // Hydrate after mount to avoid SSR/client markup mismatch.
  const [hidden, setHidden] = useState<string[]>([]);
  const [chatOpen, setChatOpen] = useState(true);
  const [presetPrompt, setPresetPrompt] = useState<string | null>(null);
  useEffect(() => {
    setHidden(loadHiddenViews(window.localStorage));
    setChatOpen(window.localStorage.getItem(CHAT_OPEN_KEY) !== "false");
  }, []);

  // Preset chip → open chat + queue the prompt; ChatPanel sends it and calls back.
  const onPreset = (prompt: string) => {
    updateChatOpen(true);
    setPresetPrompt(prompt);
  };

  const updateHidden = (next: string[]) => {
    setHidden(next);
    saveHiddenViews(window.localStorage, next);
  };
  const updateChatOpen = (open: boolean) => {
    setChatOpen(open);
    window.localStorage.setItem(CHAT_OPEN_KEY, String(open));
  };

  // Auto-activate a freshly generated view; fall back to Overview when the
  // active view's file disappears (deleted via chat).
  const knownFiles = useRef<Set<string> | null>(null);
  const fileKey = views.map((v) => v.fileName).join("|");
  useEffect(() => {
    const current = new Set(views.map((v) => v.fileName));
    if (knownFiles.current !== null) {
      const added = [...current].filter((f) => !knownFiles.current!.has(f));
      if (added.length > 0) setActive(added[0]);
    }
    knownFiles.current = current;
    // Fall back to Overview only when the active selection is neither a seed tab
    // nor an existing generated view (e.g. the active view file was deleted).
    setActive((prev) => (!isSeedTab(prev) && !current.has(prev) ? OVERVIEW_TAB : prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileKey]);

  const visibleViews = views.filter((v) => !hidden.includes(v.fileName));
  const activeSeed = SEED_TABS.find((t) => t.id === active);
  const activeView = visibleViews.find((v) => v.fileName === active);
  // Render a generated view only when it's the active selection and not a seed
  // tab; otherwise show the active seed (default to the first seed = Overview).
  const ActiveSeedComponent = (activeSeed ?? SEED_TABS[0]).Component;

  const onHide = (fileName: string) => {
    updateHidden(hideView(hidden, fileName));
    if (active === fileName) setActive(OVERVIEW_TAB);
  };

  return (
    <div className="flex h-screen">
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          views={views}
          hidden={hidden}
          onRestore={(f) => updateHidden(restoreView(hidden, f))}
          chatOpen={chatOpen}
          onOpenChat={() => updateChatOpen(true)}
        />
        <TabBar
          views={visibleViews}
          active={activeSeed || activeView ? active : OVERVIEW_TAB}
          onSelect={setActive}
          onHide={onHide}
        />
        <main className="relative min-h-0 flex-1 overflow-y-auto">
          {activeView && !activeSeed ? (
            <GeneratedViewHost view={activeView} />
          ) : (
            <ActiveSeedComponent onPreset={onPreset} />
          )}
        </main>
      </div>
      {chatOpen && (
        <ChatPanel
          onCollapse={() => updateChatOpen(false)}
          presetPrompt={presetPrompt}
          onPresetConsumed={() => setPresetPrompt(null)}
        />
      )}
    </div>
  );
}
