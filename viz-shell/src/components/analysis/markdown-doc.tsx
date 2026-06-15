"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { trpc } from "@/lib/trpc";
import type { MarkdownDoc as MarkdownDocType } from "@/server/schemas";

type DocProcedure = "watchlist" | "regime";

/**
 * Large opaque markdown doc (watchlist.md ~100KB / regime.md ~190KB). Collapsed
 * by default — these are huge, so render only on expand to keep the panel light.
 */
export function MarkdownDoc({ which, title }: { which: DocProcedure; title: string }) {
  const [open, setOpen] = useState(false);
  const query = trpc.portfolio[which].useQuery(undefined, { enabled: open });
  const doc = query.data as MarkdownDocType | null | undefined;

  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <button
        type="button"
        data-testid={`markdown-toggle-${which}`}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {doc?.stale && <span className="rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn">⚠️ stale</span>}
        </span>
        <span className="text-ink-dim">{open ? "▴ 접기" : "▾ 펼치기"}</span>
      </button>
      {open && (
        <div data-testid={`markdown-body-${which}`} className="mt-3 max-h-[60vh] overflow-y-auto border-t border-edge pt-3">
          {query.isLoading ? (
            <p className="text-sm text-ink-dim">로딩 중…</p>
          ) : doc === null || doc === undefined ? (
            <p data-testid={`markdown-empty-${which}`} className="text-sm text-ink-dim">
              {title} 문서 없음
            </p>
          ) : (
            <article className="prose-invert max-w-none text-sm leading-relaxed [&_code]:text-accent [&_h1]:mb-2 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-sm [&_h2]:font-semibold [&_li]:ml-4 [&_li]:list-disc [&_p]:mb-2 [&_table]:text-xs [&_th]:pr-3 [&_td]:pr-3">
              <ReactMarkdown>{doc.markdown}</ReactMarkdown>
            </article>
          )}
        </div>
      )}
    </div>
  );
}
