/**
 * Shared chart theming — every colour is a CSS token (``tokens.css``); the
 * ``@nexus/ui`` lint refuses raw hex/oklch here as anywhere else.
 * Series order goes from the brand primary to softer accents so a stacked
 * chart with 2–6 series stays legible in light and dark.
 */
export const CHART_SERIES_COLORS: readonly string[] = [
  "var(--color-primary)",
  "var(--color-primary-deep)",
  "var(--color-accent-mid)",
  "var(--color-status-warning)",
  "var(--color-accent-soft)",
  "var(--color-status-info)",
];

export const chartAxisProps = {
  tick: { fill: "var(--color-fg-muted)", fontSize: 11 },
  axisLine: { stroke: "var(--color-border)" },
  tickLine: false as const,
};

export const chartTooltipStyle: React.CSSProperties = {
  background: "var(--color-bg-elevated)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md, 6px)",
  color: "var(--color-fg)",
  fontSize: 12,
};
