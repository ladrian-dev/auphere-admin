"use client";

import { formatNumber } from "@nexus/ui";

import { DayBars } from "@/components/charts/day-bars";
import { useLocale, useT } from "@/i18n/client";
import type { HomeTrend } from "@/lib/backend/home-usage";

/** Conversations per day (spec 026, style 3 chosen by the owner). */
export function ConversationsChart({ trend }: { trend: HomeTrend }) {
  const t = useT();
  const locale = useLocale();
  if (trend.current === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">{t("hu.home.chart.empty")}</p>;
  }
  return (
    <DayBars
      slot="conversations-chart"
      days={trend.days}
      series={trend.series}
      byClient={trend.by_client.map((c) => ({ label: c.external_client_ref === null ? t("hu.home.chart.rest") : (c.client_name ?? c.external_client_ref), series: c.series }))}
      format={(v) => formatNumber(v, locale)}
      barLabel={(day, value) => t("hu.home.chart.bar", { day, n: value })}
      ariaLabel={t("hu.home.chart.aria")}
      averageLabel={(value) => t("hu.home.chart.avg", { n: value })}
      todayLabel={t("hu.home.chart.today")}
      emptyText={t("hu.home.chart.empty")}
    />
  );
}
