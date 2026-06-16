"use client";

/**
 * Example prompts (starting points, not commands). Clicking one DROPS it into
 * the chat input as an editable draft — the user tweaks and sends. They state
 * intent + which data to use, but leave the visual design to the agent, so they
 * read as seeds for generation rather than a fixed widget menu. The real
 * generative surface is the free-text input; these just lower the blank-page
 * cost. Add/edit freely — they carry no behavior of their own.
 */
export type Preset = { label: string; prompt: string };

export const PRESETS: Preset[] = [
  {
    label: "결정을 confidence별로",
    prompt: "Show my recent decisions grouped by confidence (trpc.portfolio.decisions).",
  },
  {
    label: "품질 지표",
    prompt: "Show the latest decision-quality metrics (trpc.portfolio.quality).",
  },
  {
    label: "스크리닝 퍼널",
    prompt:
      "Show today's screening funnel — verdicts with reasons and the scan size (trpc.portfolio.screening). Let me pick the date.",
  },
  {
    label: "센티먼트",
    prompt: "Show retail sentiment per symbol, most-discussed first (trpc.portfolio.sentiment).",
  },
  {
    label: "turns 비용",
    prompt: "Show how my agent-turn cost has trended over time (trpc.portfolio.turns).",
  },
  {
    label: "시스템 헬스",
    prompt: "Show system health — overall plus anything not OK (trpc.portfolio.health).",
  },
];

export function PresetGallery({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-1 text-sm font-semibold text-ink">
        채팅에 원하는 뷰를 말로 요청하세요
      </h2>
      <p className="mb-3 text-xs text-ink-dim">
        시드 탭에 없는 어떤 데이터든 끌어올 수 있습니다. 막막하면 아래 예시를 누르세요 —
        입력창에 채워지며, 편집 후 보내면 됩니다.
      </p>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            data-testid={`preset-${p.label}`}
            onClick={() => onPick(p.prompt)}
            title={p.prompt}
            className="rounded-full border border-edge bg-surface-0 px-3 py-1.5 text-xs text-ink hover:border-accent hover:text-accent"
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
