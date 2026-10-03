"use client";

import { DayBars } from "@/components/charts/day-bars";
import { useLocale, useT } from "@/i18n/client";
import type { UsageSpend } from "@/lib/backend/home-usage";
import { formatMoney } from "@/lib/money";

/** Spend per day in dollars (spec 028), the same bars as the home page. */
export function SpendChart({ spend }: { spend: UsageSpend }) {
  const t = useT();
  const locale = useLocale();
  return (
    <DayBars
      slot="spend-chart"
      days={spend.days}
      series={spend.series_cents}
      byClient={spend.by_client.map((c) => ({ label: c.external_client_ref === null ? t("hu.home.spend.outside") : (c.client_name ?? c.external_client_ref), series: c.series_cents }))}
      format={(cents) => formatMoney(cents, locale)}
      barLabel={(day, amount) => t("hu.usage.spend.bar", { day, amount })}
      ariaLabel={t("hu.usage.spend.aria")}
      averageLabel={(amount) => t("hu.usage.spend.avg", { amount })}
      todayLabel={t("hu.home.chart.today")}
      emptyText={t("hu.usage.spend.empty")}
    />
  );
}
