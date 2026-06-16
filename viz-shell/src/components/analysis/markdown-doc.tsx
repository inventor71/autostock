"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { trpc } from "@/lib/trpc";

type DocProcedure = "watchlist" | "regime" | "lessons" | "surge" | "daily";
type AnyDoc = { markdown: string; stale?: boolean } | null | undefined;

/**
 * Large opaque markdown doc (watchlist/regime/lessons/surge/daily). Collapsed by
 * default — some are huge (regime ~190KB), so render only on expand. Dated docs
 * (surge/daily) default to the latest; a generated view can pass a date instead.
 */
export function MarkdownDoc({ which, title }: { which: DocProcedure; title: string }) {
  const [open, setOpen] = useState(false);
  // The five doc procedures share a markdown-bearing return shape; the union of
  // their query signatures isn't inferable, so address the namespace loosely and
  // narrow the result via AnyDoc.
  const useDoc = (trpc.portfolio[which] as { useQuery: (i: undefined, o: { enabled: boolean }) => { data: unknown; isLoading: boolean } }).useQuery;
  const query = useDoc(undefined, { enabled: open });
  const doc = query.data as AnyDoc;

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
