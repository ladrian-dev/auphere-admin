"use client";

import { StackedBarChart, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { HomeTrend } from "@/lib/backend/home-usage";

import { chartData } from "./home-model";

/** Conversations per day, stacked by client (spec 026, Historia 3). */
export function ConversationsChart({ trend }: { trend: HomeTrend }) {
  const t = useT();
  const locale = useLocale();
  if (trend.current === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">{t("hu.home.chart.empty")}</p>;
  }
  const { rows, series } = chartData(trend, t("hu.home.chart.rest"));
  const day = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", { weekday: "short", day: "numeric", timeZone: "UTC" });
  return (
    <StackedBarChart
      data={rows}
      xKey="day"
      series={series}
      height={200}
      ariaLabel={t("hu.home.chart.aria")}
      formatValue={(v) => formatNumber(v, locale)}
      formatX={(x) => day.format(new Date(`${x}T00:00:00Z`))}
    />
  );
}
