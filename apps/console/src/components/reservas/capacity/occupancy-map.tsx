"use client";

import { EmptyState, cn } from "@nexus/ui";

import type { Occupancy } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { dayLabel, daysBetween, periodLabel, periodRange, shortDay } from "../model/dates";
import { heatLevel, mapColumns, scheduleTimes, slotAt, type HeatLevel } from "../model/occupancy";

/** The five levels, from tokens only: the primary green at 10, 30 and 55 %, the deep green, and ink for full. */
export const HEAT_CLASS: Record<HeatLevel, string> = {
  l1: "bg-primary/10 text-foreground",
  l2: "bg-primary/30 text-foreground",
  l3: "bg-primary/55 text-foreground",
  l4: "bg-primary-deep text-fg-on-dark",
  full: "bg-foreground text-background",
};

/** «Bloqueado» as a 135° stripe of two surface tokens: readable in light and dark. */
export const BLOCKED_CLASS =
  "bg-[repeating-linear-gradient(135deg,var(--color-bg-sunken)_0_6px,var(--color-bg)_6px_12px)] text-foreground";

/**
 * The occupancy map of Aforo (spec 043, T024; design 2a): one row per day of
 * the period, one column per arrival time grouped under its shift. Each cell
 * says how many people are inside, «Lleno», «Bloq.» or «–» when closed;
 * past cells are dimmed. A cell opens the hour panel.
 */
export function OccupancyMap({ occupancy }: { occupancy: Occupancy }) {
  const { t, locale, url, today, settings, open } = useReservas();
  const words = useWords();
  const range = periodRange(url.period, url.date);
  const days = daysBetween(range.from, range.to);
  const byDate = new Map(occupancy.days.map((d) => [d.date, d]));
  const groups = mapColumns(occupancy.days, scheduleTimes(settings.capacity?.schedule));
  const { seats, walkin_hold: hold } = occupancy;

  if (groups.length === 0) {
    return <EmptyState title={t("reservas.map.noSchedule")} readonly />;
  }
  if (occupancy.days.length > 0 && occupancy.days.every((d) => d.closed)) {
    return <EmptyState title={t("reservas.map.allClosed")} readonly />;
  }
  const hasShifts = groups.some((g) => g.shift);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="min-w-0 overflow-x-auto rounded-md border border-border bg-card">
        <table className="w-full min-w-max border-separate border-spacing-1 p-2 text-xs">
          <caption className="sr-only">{t("reservas.map.label", { period: periodLabel(url.period, url.date, locale) })}</caption>
          <thead>
            {hasShifts ? (
              <tr>
                <td />
                {groups.map((g, i) => (
                  <th key={`${g.shift ?? ""}-${i}`} scope="colgroup" colSpan={g.times.length} className="px-1 pb-1 text-left text-xs font-medium text-muted-foreground">
                    {g.shift}
                  </th>
                ))}
              </tr>
            ) : null}
            <tr>
              <th scope="col" className="sr-only">
                {t("reservas.map.day")}
              </th>
              {groups.flatMap((g) =>
                g.times.map((time) => (
                  <th key={time} scope="col" className="px-1 text-center font-normal text-muted-foreground tabular-nums">
                    {time}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {days.map((date) => {
              const day = byDate.get(date);
              const label = dayLabel(date, locale);
              return (
                <tr key={date}>
                  <th scope="row" className="pr-2 text-left font-medium whitespace-nowrap">
                    <span className={cn("inline-flex items-center gap-2", date === today && "text-primary-text")}>
                      {url.period === "day" ? words.dayTitle(date) : shortDay(date, locale)}
                      {date === today && url.period !== "day" ? (
                        <span className="rounded-full bg-accent px-2 text-xs text-accent-foreground">{t("reservas.toolbar.today.day")}</span>
                      ) : null}
                    </span>
                  </th>
                  {groups.flatMap((g) =>
                    g.times.map((time) => {
                      const slot = slotAt(day, time);
                      if (!day || day.closed || !slot) {
                        return (
                          <td key={time} className="h-10 min-w-12 rounded-sm bg-muted/40 text-center text-muted-foreground">
                            <span aria-hidden="true">–</span>
                            <span className="sr-only">{t("reservas.map.cell.ariaClosed", { day: label, time })}</span>
                          </td>
                        );
                      }
                      const level = heatLevel(slot.present, seats, hold);
                      const aria = slot.blocked
                        ? t("reservas.map.cell.ariaBlocked", { day: label, time, label: slot.blocked.label })
                        : level === "full"
                          ? t("reservas.map.cell.ariaFull", { day: label, time })
                          : t("reservas.map.cell.aria", { day: label, time, present: slot.present, seats, unit: words.unit });
                      return (
                        <td key={time} className="h-10 min-w-12 p-0">
                          <button
                            type="button"
                            aria-label={aria}
                            onClick={() => open({ kind: "hour", date, time })}
                            className={cn(
                              "flex size-full min-h-10 items-center justify-center rounded-sm px-1 font-medium tabular-nums",
                              "transition-[filter] duration-(--duration-hover) hover:brightness-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                              slot.blocked ? BLOCKED_CLASS : HEAT_CLASS[level],
                              slot.past && "opacity-60",
                            )}
                          >
                            {slot.blocked ? t("reservas.map.blocked") : level === "full" ? t("reservas.map.full") : slot.present}
                          </button>
                        </td>
                      );
                    }),
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Legend />
    </div>
  );
}

function Legend() {
  const { t } = useReservas();
  const items: { key: string; cls: string; label: string }[] = [
    { key: "l1", cls: HEAT_CLASS.l1, label: t("reservas.legend.l1") },
    { key: "l2", cls: HEAT_CLASS.l2, label: t("reservas.legend.l2") },
    { key: "l3", cls: HEAT_CLASS.l3, label: t("reservas.legend.l3") },
    { key: "l4", cls: HEAT_CLASS.l4, label: t("reservas.legend.l4") },
    { key: "full", cls: HEAT_CLASS.full, label: t("reservas.legend.full") },
    { key: "blocked", cls: BLOCKED_CLASS, label: t("reservas.legend.blocked") },
  ];
  return (
    <ul aria-label={t("reservas.legend.label")} className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
      {items.map((i) => (
        <li key={i.key} className="inline-flex items-center gap-2">
          <span aria-hidden="true" className={cn("size-4 rounded-sm border border-border", i.cls)} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
