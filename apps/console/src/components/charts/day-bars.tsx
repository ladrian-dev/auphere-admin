"use client";

import { cn } from "@nexus/ui";

import { useLocale } from "@/i18n/client";

import { type DayBarsInput, buildDayBars, showDayLabel } from "./day-bars-model";

type Props = DayBarsInput & {
  /** How a value reads: a count, or money. */
  format: (value: number) => string;
  /** The accessible name of a bar: «jueves 1: 1500 conversaciones». */
  barLabel: (day: string, value: string) => string;
  ariaLabel: string;
  averageLabel: (value: string) => string;
  todayLabel: string;
  emptyText: string;
  slot?: string;
};

/**
 * One total per day in one colour, today in the strong colour, the daily
 * average as a dashed line, and on hover or keyboard focus the day's total
 * with its three biggest series. Plain HTML: a few bars do not need a chart
 * library (owner's pick, 2026-10-02).
 */
export function DayBars({ format, barLabel, ariaLabel, averageLabel, todayLabel, emptyText, slot, ...input }: Props) {
  const locale = useLocale();
  const { bars, average, max } = buildDayBars(input);
  if (bars.every((b) => b.total === 0)) {
    return <p className="py-12 text-center text-sm text-muted-foreground">{emptyText}</p>;
  }
  const dense = bars.length > 14;
  const fmt = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", dense ? { day: "numeric", month: "short", timeZone: "UTC" } : { weekday: "short", timeZone: "UTC" });
  const full = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", { weekday: "long", day: "numeric", month: dense ? "short" : undefined, timeZone: "UTC" });
  const date = (d: string) => new Date(`${d}T00:00:00Z`);
  return (
    <div className="flex flex-col gap-2" data-slot={slot ?? "day-bars"}>
      <p className="text-right text-xs text-muted-foreground">{averageLabel(format(Math.round(average)))}</p>
      <div className="relative h-40">
        <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 border-t border-dashed border-muted-foreground/60" style={{ bottom: `${(average / max) * 100}%` }} />
        <ul className={cn("flex h-full items-end", dense ? "gap-px" : "gap-2")} aria-label={ariaLabel}>
          {bars.map((bar, i) => {
            const label = barLabel(full.format(date(bar.day)), format(bar.total));
            const align = i < bars.length / 4 ? "left-0" : i > (bars.length * 3) / 4 ? "right-0" : "left-1/2 -translate-x-1/2";
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
                      <span className="tabular-nums">{format(c.value)}</span>
                    </span>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <ul aria-hidden="true" className={cn("flex text-xs text-muted-foreground", dense ? "gap-px" : "gap-2")}>
        {bars.map((bar, i) => (
          <li key={bar.day} className={cn("flex-1 overflow-visible text-center whitespace-nowrap", bar.today && "font-medium text-foreground")}>
            {showDayLabel(i, bars.length) ? (bar.today ? todayLabel : fmt.format(date(bar.day))) : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
