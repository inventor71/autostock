/**
 * Shared recharts dark-theme constants — keep seed and generated views on the
 * same palette (mirrors the CSS tokens in globals.css).
 */
export const CHART_GRID_STROKE = "#232b3d"; // --color-edge
export const CHART_AXIS_STROKE = "#8b93a7"; // --color-ink-dim
export const CHART_ACCENT = "#7aa2f7"; // --color-accent

export const CHART_TOOLTIP_STYLE = {
  background: "#11151f", // --color-surface-1
  border: "1px solid #232b3d",
  borderRadius: 8,
  color: "#d7dce6", // --color-ink
  fontSize: 12,
} as const;
