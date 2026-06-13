"use client";

import ReactMarkdown from "react-markdown";

import { trpc } from "@/lib/trpc";

export function ThesisDrawer({
  symbol,
  onClose,
}: {
  symbol: string;
  onClose: () => void;
}) {
  const { data: doc, isLoading } = trpc.portfolio.thesis.useQuery({ symbol });

  return (
    <div className="absolute inset-y-0 right-0 z-20 flex w-full max-w-xl flex-col border-l border-edge bg-surface-1 shadow-2xl">
      <div className="flex items-center justify-between border-b border-edge px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-ink">{symbol} — Thesis</h2>
          {doc?.stale && (
            <span
              data-testid="thesis-stale-badge"
              title="파일이 읽는 동안 계속 변경됨 — 마지막 읽기 본문 표시"
              className="rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn"
            >
              ⚠️ stale
            </span>
          )}
        </div>
        <button
          type="button"
          data-testid="thesis-drawer-close"
          onClick={onClose}
          className="rounded px-2 py-1 text-ink-dim hover:bg-surface-2 hover:text-ink"
          aria-label="닫기"
        >
          ✕
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {isLoading ? (
          <p className="text-sm text-ink-dim">로딩 중…</p>
        ) : doc === null || doc === undefined ? (
          <p data-testid="thesis-empty" className="text-sm text-ink-dim">
            {symbol} thesis 문서 없음
          </p>
        ) : (
          <article className="prose-invert max-w-none text-sm leading-relaxed [&_a]:text-accent [&_code]:text-accent [&_h1]:mb-2 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-base [&_h2]:font-semibold [&_li]:ml-4 [&_li]:list-disc [&_p]:mb-2">
            <ReactMarkdown>{doc.markdown}</ReactMarkdown>
          </article>
        )}
      </div>
    </div>
  );
}
