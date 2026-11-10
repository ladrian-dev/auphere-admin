"use client";

import { CalendarClock, Clock, Scissors, Users } from "lucide-react";
import Link from "next/link";

import { Button, ErrorState } from "@nexus/ui";

import type { Booking, StaffMember } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { dayLabel, daysBetween, periodLabel, periodRange, shortDay, weekdayOf } from "../model/dates";
import { bookedPercent, bookingSpan, gridBounds, holdsTime, spansOf } from "../model/day-grid";
import { heldSlots } from "../model/waitlist";
import { ChipGroup, Chip, Initials } from "../shared";
import { Toolbar } from "../toolbar";
import { MonthGrid } from "./month-grid";
import { ServicesList } from "./services-list";
import { TimeGrid, type GridColumn } from "./time-grid";

/**
 * The Agenda tab of Servicios (spec 043, T023): the toolbar, then the grid of
 * the period (day by professional, one professional's week, the month) or the
 * list. Without a team or services there is nothing to book with: it says how
 * to start instead of painting a calendar that looks broken (Casos límite).
 */
export function ServicesAgenda() {
  const ctx = useReservas();
  const { data, t } = ctx;
  const { staff, services, bookings } = data;

  if (staff === null || services === null) {
    return <ErrorState title={t("reservas.error.title")} description={t("reservas.error.body")} onRetry={ctx.refresh} retryLabel={t("common.retry")} />;
  }
  if (staff.length === 0 || services.length === 0) return <StartHere />;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Toolbar staff={staff} />
      {bookings === null ? (
        <ErrorState title={t("reservas.error.title")} description={t("reservas.error.body")} onRetry={ctx.refresh} />
      ) : ctx.url.view === "list" ? (
        <ServicesList staff={staff} />
      ) : ctx.url.period === "month" ? (
        <MonthGrid staff={ctx.url.staff ? staff.filter((s) => s.id === ctx.url.staff) : staff} />
      ) : ctx.url.period === "week" ? (
        <WeekGrid staff={staff} />
      ) : (
        <DayGrid staff={ctx.url.staff ? staff.filter((s) => s.id === ctx.url.staff) : staff} />
      )}
      <p className="text-xs text-muted-foreground">{t("reservas.grid.legend")}</p>
    </div>
  );
}

function StartHere() {
  const { t, href } = useReservas();
  const steps = [
    { icon: Users, key: "reservas.start.staff" as const },
    { icon: Scissors, key: "reservas.start.services" as const },
    { icon: Clock, key: "reservas.start.hours" as const },
  ];
  return (
    <section
      role="status"
      className="flex min-w-0 flex-col items-center gap-4 rounded-md border border-dashed border-border bg-card px-6 py-12 text-center"
    >
      <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
        <CalendarClock className="size-5" aria-hidden="true" />
      </span>
      <h2 className="text-base font-medium text-balance">{t("reservas.start.title")}</h2>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("reservas.start.body")}</p>
      <ol className="flex flex-col gap-2 text-left text-sm">
        {steps.map(({ icon: Icon, key }, i) => (
          <li key={key} className="flex items-center gap-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
              {i + 1}
            </span>
            <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="text-pretty">{t(key)}</span>
          </li>
        ))}
      </ol>
      <Button nativeButton={false} render={<Link href={href({ tab: "settings" })} />}>{t("reservas.start.action")}</Button>
    </section>
  );
}

function bookingsOf(list: readonly Booking[], date: string, staffId: string): Booking[] {
  return list.filter((b) => b.local.date === date && b.staff?.id === staffId);
}

function closedOn(date: string, closedDays: readonly string[]): boolean {
  return closedDays.includes(date);
}

/** What the grid must fit: the bookings that hold their time and the slots held for the waitlist. */
function columnItems(columns: readonly GridColumn[]) {
  return columns.flatMap((c) => [...c.bookings.filter(holdsTime), ...(c.held ?? [])].map(bookingSpan));
}

function DayGrid({ staff }: { staff: StaffMember[] }) {
  const { t, locale, url, bookings, data, open } = useReservas();
  const words = useWords();
  const date = url.date;
  const closedDays = data.bookings?.closed_days ?? [];
  const columns: GridColumn[] = staff.map((s) => {
    const spans = closedOn(date, closedDays) ? [] : spansOf(s.effective_hours[weekdayOf(date)]);
    const list = bookingsOf(bookings, date, s.id);
    const count = list.filter(holdsTime).length;
    return {
      key: s.id,
      date,
      staff: { id: s.id, name: s.name },
      spans,
      bookings: list,
      held: heldSlots(data.offers?.running, date, s.id),
      freeLabel: (time) => t("reservas.grid.free.aria", { time, name: s.name }),
      header: (
        <>
          <Initials name={s.name} />
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-medium" title={s.name}>
              {s.name}
            </span>
            <span className="truncate text-xs text-muted-foreground">
              {t("reservas.grid.meta", { bookings: words.bookings(count), pct: bookedPercent(spans, list) })}
            </span>
          </span>
        </>
      ),
    };
  });
  const bounds = gridBounds(columns.map((c) => c.spans), columnItems(columns));
  return (
    <TimeGrid
      label={t("reservas.grid.label", { day: dayLabel(date, locale) })}
      columns={columns}
      bounds={bounds}
      onFree={(c, time) => open({ kind: "new", prefill: { date: c.date, time, staffId: c.staff?.id } })}
    />
  );
}

function WeekGrid({ staff }: { staff: StaffMember[] }) {
  const { t, locale, url, bookings, data, open, go, today } = useReservas();
  const words = useWords();
  const current = staff.find((s) => s.id === url.staff) ?? staff[0]!;
  const closedDays = data.bookings?.closed_days ?? [];
  const { from, to } = periodRange("week", url.date);
  const columns: GridColumn[] = daysBetween(from, to).map((date) => {
    const spans = closedOn(date, closedDays) ? [] : spansOf(current.effective_hours[weekdayOf(date)]);
    const list = bookingsOf(bookings, date, current.id);
    return {
      key: date,
      date,
      staff: { id: current.id, name: current.name },
      spans,
      bookings: list,
      held: heldSlots(data.offers?.running, date, current.id),
      highlight: date === today,
      freeLabel: (time) => t("reservas.grid.free.ariaDay", { day: dayLabel(date, locale), time }),
      header: (
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-medium">{shortDay(date, locale)}</span>
          <span className="truncate text-xs text-muted-foreground">{words.bookings(list.filter(holdsTime).length)}</span>
        </span>
      ),
    };
  });
  const bounds = gridBounds(columns.map((c) => c.spans), columnItems(columns));
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {staff.length > 1 ? (
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">{t("reservas.staff.weekOf")}</span>
          <ChipGroup label={t("reservas.staff.weekOf")}>
            {staff.map((s) => (
              <Chip key={s.id} pressed={s.id === current.id} onClick={() => go({ staff: s.id })}>
                {s.name}
              </Chip>
            ))}
          </ChipGroup>
        </div>
      ) : null}
      <TimeGrid
        label={t("reservas.grid.weekLabel", { name: `${current.name} · ${periodLabel("week", url.date, locale)}` })}
        columns={columns}
        bounds={bounds}
        onFree={(c, time) => open({ kind: "new", prefill: { date: c.date, time, staffId: current.id } })}
      />
    </div>
  );
}
