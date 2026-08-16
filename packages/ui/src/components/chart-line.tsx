"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { cn } from "../lib/utils";
import { CHART_SERIES_COLORS, chartAxisProps, chartTooltipStyle } from "./chart-theme";

type Point = { x: string; actual?: number | null; projected?: number | null };

type ProjectionLineChartProps = {
  /** Cumulative points; ``actual`` up to today, ``projected`` from today on. */
  data: Point[];
  labels: { actual: string; projected: string; cap?: string };
  /** Horizontal reference line (the monthly cap), if any. */
  cap?: number | null;
  formatValue?: (n: number) => string;
  formatX?: (x: string) => string;
  height?: number;
  className?: string;
  ariaLabel: string;
};

/**
 * Cumulative line with a dashed linear projection to the end of the
 * period and an optional cap line (CP-22). Same token palette as the bars.
 */
function ProjectionLineChart({ data, labels, cap, formatValue, formatX, height = 220, className, ariaLabel }: ProjectionLineChartProps) {
  const fmt = formatValue ?? ((n: number) => String(n));
  return (
    <div className={cn("w-full min-w-0", className)} role="img" aria-label={ariaLabel} data-slot="chart-line">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--color-border-soft)" />
          <XAxis dataKey="x" tickFormatter={formatX} {...chartAxisProps} />
          <YAxis tickFormatter={(v: number) => fmt(v)} width={56} {...chartAxisProps} />
          <Tooltip
            contentStyle={chartTooltipStyle}
            formatter={(v: unknown, name: unknown) => [fmt(Number(v)), name === "actual" ? labels.actual : labels.projected]}
            labelFormatter={(l: unknown) => (formatX ? formatX(String(l)) : String(l))}
          />
          {cap != null && cap > 0 ? (
            <ReferenceLine y={cap} stroke="var(--color-status-danger)" strokeDasharray="4 4" label={{ value: labels.cap ?? "", position: "insideTopRight", fill: "var(--color-fg-muted)", fontSize: 11 }} />
          ) : null}
          <Line type="monotone" dataKey="actual" name="actual" stroke={CHART_SERIES_COLORS[0]} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="projected" name="projected" stroke={CHART_SERIES_COLORS[1]} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export { ProjectionLineChart, type ProjectionLineChartProps };
