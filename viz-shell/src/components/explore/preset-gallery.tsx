"use client";

/**
 * Preset chips — each is a seed PROMPT (not a hardcoded widget). Clicking one
 * sends it to the chat agent, which generates a view in src/generated/. This is
 * the vibeOS shift: exploratory data is generated on demand, not pre-drawn.
 */
export type Preset = { label: string; prompt: string };

export const PRESETS: Preset[] = [
  {
    label: "결정을 confidence별로",
    prompt:
      "Create a view at src/generated/decisions-by-confidence.tsx: bar chart of trpc.portfolio.decisions({limit:200}) bucketed by confidence (0–0.5, 0.5–0.7, 0.7–0.9, 0.9–1.0). Use recharts + @/lib/chart-theme.",
  },
  {
    label: "품질 지표 시계열",
    prompt:
      "Create src/generated/quality-trends.tsx: show trpc.portfolio.quality() latest metrics (direction hit rate, target reach, realized RR) as labeled cards with the as-of date.",
  },
  {
    label: "스크리닝 퍼널",
    prompt:
      "Create src/generated/screening-funnel-view.tsx using trpc.portfolio.screening(): a table of verdicts (symbol, verdict, reason) plus the scan count, with a date picker built from the returned `dates` array.",
  },
  {
    label: "센티먼트 막대",
    prompt:
      "Create src/generated/sentiment-bars.tsx from trpc.portfolio.sentiment(): per-symbol bull/bear horizontal bars, ranked by total volume.",
  },
  {
    label: "turns 비용 추이",
    prompt:
      "Create src/generated/turn-cost.tsx: line chart of trpc.portfolio.turns({limit:100}) cumulative cost_usd over time, recharts.",
  },
  {
    label: "시스템 헬스",
    prompt:
      "Create src/generated/health-view.tsx from trpc.portfolio.health(): overall verdict + per-dimension status with non-OK checks highlighted.",
  },
];

export function PresetGallery({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-1 p-4">
      <h2 className="mb-1 text-sm font-semibold text-ink">커스텀 뷰 만들기</h2>
      <p className="mb-3 text-xs text-ink-dim">
        칩을 누르면 채팅이 해당 뷰를 생성합니다. 또는 채팅에 원하는 걸 직접 적어도 됩니다 —
        시드 탭에 없는 어떤 데이터든 끌어올 수 있습니다.
      </p>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            data-testid={`preset-${p.label}`}
            onClick={() => onPick(p.prompt)}
            className="rounded-full border border-edge bg-surface-0 px-3 py-1.5 text-xs text-ink hover:border-accent hover:text-accent"
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
