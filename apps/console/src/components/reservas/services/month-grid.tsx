"use client";

import { cn } from "@nexus/ui";

import type { StaffMember } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { dayLabel, monthLabel, monthWeeks, weekdayOf, weekdayShort } from "../model/dates";
import { bookedPercent, holdsTime, spansOf } from "../model/day-grid";

/**
 * The month of Servicios (spec 043, T023): a Monday-first calendar where each
 * day says «N reservas» with its occupancy bar (dark from 85 %), «Cerrado»
 * when the business does not open, and opens the day on a click.
 */
export function MonthGrid({ staff }: { staff: StaffMember[] }) {
  const { t, locale, url, bookings, data, settings, today, go } = useReservas();
  const words = useWords();
  const weeks = monthWeeks(url.date);
  const month = url.date.slice(0, 7);
  const closedDays = data.bookings?.closed_days ?? [];
  const staffIds = new Set(staff.map((s) => s.id));

  return (
    <section aria-label={t("reservas.month.label", { month: monthLabel(url.date, locale) })} className="min-w-0 overflow-x-auto rounded-md border border-border bg-card">
      <div className="grid min-w-84 grid-cols-7">
        {weeks[0]!.map((d) => (
          <div key={d} aria-hidden="true" className="border-b border-border px-2 py-2 text-xs font-medium text-muted-foreground">
            {weekdayShort(d, locale)}
          </div>
        ))}
        {weeks.flat().map((d) => {
          if (d.slice(0, 7) !== month) {
            return <div key={d} aria-hidden="true" className="min-h-20 border-b border-l border-border bg-muted/40 first:border-l-0" />;
          }
          const weekday = weekdayOf(d);
          const closed = closedDays.includes(d) || settings.business_hours[weekday].length === 0;
          const list = bookings.filter((b) => b.local.date === d && holdsTime(b) && (!b.staff || staffIds.has(b.staff.id)));
          const spans = staff.flatMap((s) => spansOf(s.effective_hours[weekday]));
          const pct = closed ? 0 : bookedPercent(spans, list);
          const count = words.bookings(list.length);
          return (
            <button
              key={d}
              type="button"
              onClick={() => go({ period: "day", date: d })}
              aria-label={
                closed
                  ? t("reservas.month.day.closedAria", { day: dayLabel(d, locale) })
                  : t("reservas.month.day.aria", { day: dayLabel(d, locale), bookings: count, pct })
              }
              className={cn(
                "flex min-h-20 min-w-0 flex-col items-stretch gap-1 border-b border-l border-border p-2 text-left",
                "transition-colors duration-(--duration-hover) hover:bg-muted focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring",
                closed && "bg-muted/40",
              )}
            >
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full text-xs font-semibold tabular-nums",
                  d === today && "bg-primary text-primary-foreground",
                )}
              >
                {Number(d.slice(8))}
              </span>
              {closed ? (
                <span className="truncate text-xs text-muted-foreground">{t("reservas.month.closed")}</span>
              ) : (
                <>
                  <span className="truncate text-xs">{count}</span>
                  <span aria-hidden="true" className="mt-auto h-1 w-full overflow-hidden rounded-full bg-muted">
                    <span className={cn("block h-full rounded-full", pct >= 85 ? "bg-primary-deep" : "bg-primary")} style={{ width: `${pct}%` }} />
                  </span>
                </>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
