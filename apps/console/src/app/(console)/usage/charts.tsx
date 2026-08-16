"use client";

import { CapGauge, ProjectionLineChart, StackedBarChart, formatDate, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

type Props = {
  bars: Record<string, string | number>[];
  barSeries: { key: string; label: string }[];
  line: { x: string; actual: number | null; projected: number | null }[];
  cap: number | null;
  monthUnits: number;
  percent: number | null;
};

/** Client island of the usage page: Recharts needs the DOM; data is shaped on the server. */
export function UsageCharts({ bars, barSeries, line, cap, monthUnits, percent }: Props) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const d = (x: string) => formatDate(x, locale).replace(/\s?\d{4}$/, "");
  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section aria-label={t("hu.usage.chart.daily")} className="min-w-0 rounded-md bg-card p-4 ring-1 ring-foreground/10">
        <h3 className="mb-2 font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">{t("hu.usage.chart.daily")}</h3>
        {bars.length === 0 || barSeries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("hu.usage.chart.empty")}</p>
        ) : (
          <StackedBarChart ariaLabel={t("hu.usage.chart.daily")} data={bars} xKey="day" series={barSeries} formatValue={n} formatX={d} height={260} />
        )}
      </section>
      <div className="flex min-w-0 flex-col gap-6">
        <section aria-label={t("hu.usage.gauge")} className="rounded-md bg-card p-4 ring-1 ring-foreground/10">
          <CapGauge
            label={t("hu.usage.gauge")}
            value={monthUnits}
            max={cap}
            valueLabel={cap != null ? `${n(monthUnits)} / ${n(cap)}` : n(monthUnits)}
            percentLabel={percent != null ? t("hu.usage.month.percent", { percent: n(percent) }) : undefined}
            noCapLabel={t("hu.usage.month.nocap")}
          />
        </section>
        <section aria-label={t("hu.usage.chart.projection")} className="min-w-0 rounded-md bg-card p-4 ring-1 ring-foreground/10">
          <h3 className="mb-2 font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">{t("hu.usage.chart.projection")}</h3>
          <ProjectionLineChart
            ariaLabel={t("hu.usage.chart.projection")}
            data={line}
            labels={{ actual: t("hu.usage.chart.actual"), projected: t("hu.usage.chart.projected"), cap: t("hu.usage.chart.cap") }}
            cap={cap}
            formatValue={n}
            formatX={d}
            height={180}
          />
        </section>
      </div>
    </div>
  );
}
