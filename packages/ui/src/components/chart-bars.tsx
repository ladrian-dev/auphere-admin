"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { cn } from "../lib/utils";
import { CHART_SERIES_COLORS, chartAxisProps, chartTooltipStyle } from "./chart-theme";

type Series = { key: string; label: string };
type Row = Record<string, string | number | null | undefined>;

type StackedBarChartProps = {
  /** One row per x value; series values under their ``key``. */
  data: Row[];
  /** Key of the x value in each row (a date string, a client name…). */
  xKey: string;
  series: Series[];
  /** Formats a number for the axis and tooltip (Intl in the caller). */
  formatValue?: (n: number) => string;
  /** Formats the x tick (e.g. a date). */
  formatX?: (x: string) => string;
  height?: number;
  className?: string;
  /** Screen-reader description of the chart. */
  ariaLabel: string;
};

/**
 * Stacked bars — one bar per x, one segment per series (usage per day
 * split by meter, PLAN-CONSOLE-V1 CP-22). Colours come from the token
 * palette (``chart-theme``), never inline hex. Recharts (MIT); Tremor was
 * ruled out because it wants a legacy Tailwind config that fights the
 * project's v4 CSS-first setup and the ``@nexus/ui`` token lint.
 */
function StackedBarChart({ data, xKey, series, formatValue, formatX, height = 240, className, ariaLabel }: StackedBarChartProps) {
  const fmt = formatValue ?? ((n: number) => String(n));
  return (
    <div className={cn("w-full min-w-0", className)} role="img" aria-label={ariaLabel} data-slot="chart-bars">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--color-border-soft)" />
          <XAxis dataKey={xKey} tickFormatter={formatX} {...chartAxisProps} />
          <YAxis tickFormatter={(v: number) => fmt(v)} width={56} {...chartAxisProps} />
          <Tooltip
            cursor={{ fill: "var(--color-bg-sunken)" }}
            contentStyle={chartTooltipStyle}
            formatter={(v: unknown, name: unknown) => [fmt(Number(v)), String(series.find((s) => s.key === name)?.label ?? name)]}
            labelFormatter={(l: unknown) => (formatX ? formatX(String(l)) : String(l))}
          />
          {series.length > 1 ? <Legend formatter={(k: string) => series.find((s) => s.key === k)?.label ?? k} /> : null}
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.key} stackId="a" fill={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]} radius={i === series.length - 1 ? [2, 2, 0, 0] : 0} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export { StackedBarChart, type StackedBarChartProps };
