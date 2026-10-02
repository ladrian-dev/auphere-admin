"use client";

import { cn, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { HomeTrend } from "@/lib/backend/home-usage";

import { dayBars } from "./home-model";

/**
 * Conversations per day (spec 026, style 3 chosen by the owner): one total
 * per day in one colour, today marked, the daily average as a dashed line,
 * and on hover or focus the day's total with its three busiest clients.
 * Plain HTML, no chart library: seven bars do not need one.
 */
export function ConversationsChart({ trend }: { trend: HomeTrend }) {
  const t = useT();
  const locale = useLocale();
  if (trend.current === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">{t("hu.home.chart.empty")}</p>;
  }
  const n = (v: number) => formatNumber(v, locale);
  const { bars, average, max } = dayBars(trend, t("hu.home.chart.rest"));
  const weekday = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", { weekday: "short", timeZone: "UTC" });
  const full = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", { weekday: "long", day: "numeric", timeZone: "UTC" });
  const date = (d: string) => new Date(`${d}T00:00:00Z`);
  return (
    <div className="flex flex-col gap-2" data-slot="conversations-chart">
      <p className="text-right text-xs text-muted-foreground">{t("hu.home.chart.avg", { n: n(Math.round(average)) })}</p>
      <div className="relative h-40">
        <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 border-t border-dashed border-muted-foreground/60" style={{ bottom: `${(average / max) * 100}%` }} />
        <ul className="flex h-full items-end gap-2" aria-label={t("hu.home.chart.aria")}>
          {bars.map((bar, i) => {
            const label = t("hu.home.chart.bar", { day: full.format(date(bar.day)), n: n(bar.total) });
            const align = i === 0 ? "left-0" : i === bars.length - 1 ? "right-0" : "left-1/2 -translate-x-1/2";
            return (
              <li key={bar.day} className="group relative flex h-full flex-1 flex-col justify-end">
                <div
                  tabIndex={0}
                  aria-label={label}
                  className={cn("min-h-1 w-full rounded-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", bar.today ? "bg-primary" : "bg-primary/30 group-hover:bg-primary/50")}
                  style={{ height: `${(bar.total / max) * 100}%` }}
                />
                <div role="tooltip" className={cn("pointer-events-none absolute bottom-full z-10 mb-2 hidden w-max min-w-36 flex-col gap-1 rounded-md bg-popover p-2 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10 group-focus-within:flex group-hover:flex", align)}>
                  <span className="font-medium">{label}</span>
                  {bar.top.map((c) => (
                    <span key={c.label} className="flex justify-between gap-4 text-muted-foreground">
                      <span className="truncate">{c.label}</span>
                      <span className="tabular-nums">{n(c.value)}</span>
                    </span>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <ul aria-hidden="true" className="flex gap-2 text-xs text-muted-foreground">
        {bars.map((bar) => (
          <li key={bar.day} className={cn("flex-1 text-center", bar.today && "font-medium text-foreground")}>
            {bar.today ? t("hu.home.chart.today") : weekday.format(date(bar.day))}
          </li>
        ))}
      </ul>
    </div>
  );
}
