"use client";

import * as React from "react";

import { Alert, AlertDescription, EmptyState, cn } from "@nexus/ui";

import type { Booking, StaffMember } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { capitalize, dayLabel, formatMinutes, periodLabel } from "../model/dates";
import { bookingSpan } from "../model/day-grid";
import { AgentMark, BookingStatus, Chip, ChipGroup } from "../shared";

export type ListFilter = "all" | "pending" | "agent" | "cancelled";

export function filterBookings(list: readonly Booking[], filter: ListFilter, staffId: string | null): Booking[] {
  return list.filter((b) => {
    if (staffId && b.staff?.id !== staffId) return false;
    if (filter === "pending") return b.status === "pending";
    if (filter === "agent") return b.origin === "agent";
    if (filter === "cancelled") return b.status === "cancelled";
    return true;
  });
}

/**
 * The list of Servicios (spec 043, T023): «Todas · Sin confirmar · Del agente
 * · Canceladas», grouped by day — «Martes, 6 de octubre · hoy · 4 reservas» —
 * with time and length, client and service, professional, status and origin.
 */
export function ServicesList({ staff }: { staff: StaffMember[] }) {
  const { t, locale, url, bookings, data, today, open } = useReservas();
  const words = useWords();
  const [filter, setFilter] = React.useState<ListFilter>("all");
  const shown = filterBookings(bookings, filter, url.staff);
  const days = [...new Set(shown.map((b) => b.local.date))].sort();
  const many = staff.length > 1;

  const originLabel = (b: Booking) =>
    b.origin === "agent"
      ? t("reservas.list.origin.agent")
      : b.origin === "waitlist"
        ? t("reservas.list.origin.waitlist")
        : b.origin === "walkin"
          ? t("reservas.list.origin.walkin")
          : b.created_by.name || t("reservas.list.origin.person");

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ChipGroup label={t("reservas.list.filter")}>
        {(["all", "pending", "agent", "cancelled"] as const).map((f) => (
          <Chip key={f} pressed={filter === f} onClick={() => setFilter(f)}>
            {t(`reservas.list.filter.${f}`)}
          </Chip>
        ))}
      </ChipGroup>
      {data.bookings?.truncated ? (
        <Alert role="status">
          <AlertDescription>{t("reservas.list.truncated")}</AlertDescription>
        </Alert>
      ) : null}
      {days.length === 0 ? (
        <EmptyState title={t("reservas.list.empty")} readonly />
      ) : (
        <section aria-label={t("reservas.list.label", { period: periodLabel(url.period, url.date, locale) })} className="flex min-w-0 flex-col gap-6">
          {days.map((d) => {
            const items = shown.filter((b) => b.local.date === d);
            const head = capitalize(dayLabel(d, locale));
            return (
              <div key={d} className="flex min-w-0 flex-col gap-2">
                <h3 className="text-sm font-medium text-balance">
                  {d === today
                    ? t("reservas.list.dayToday", { day: head, bookings: words.bookings(items.length) })
                    : t("reservas.list.day", { day: head, bookings: words.bookings(items.length) })}
                </h3>
                <ul className="flex min-w-0 flex-col divide-y divide-border rounded-md border border-border bg-card">
                  {items.map((b) => {
                    const s = bookingSpan(b);
                    return (
                      <li key={b.id}>
                        <button
                          type="button"
                          onClick={() => open({ kind: "detail", id: b.id, booking: b })}
                          className={cn(
                            "flex w-full min-w-0 flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left",
                            "transition-colors duration-(--duration-hover) hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring",
                            b.status === "cancelled" && "text-muted-foreground",
                          )}
                        >
                          <span className="flex w-20 shrink-0 flex-col tabular-nums">
                            <span className="text-sm font-medium">{b.local.start}</span>
                            <span className="text-xs text-muted-foreground">{formatMinutes(s.to - s.from)}</span>
                          </span>
                          <span className="flex min-w-0 flex-1 basis-40 flex-col">
                            <span className="flex min-w-0 items-center gap-1 text-sm font-medium">
                              <span className="truncate" title={b.contact.name ?? undefined}>
                                {b.contact.name}
                              </span>
                              {b.origin === "agent" ? <AgentMark /> : null}
                            </span>
                            <span className="truncate text-xs text-muted-foreground">{b.service?.name}</span>
                          </span>
                          {many && b.staff ? (
                            <span className="w-28 min-w-0 shrink-0 truncate text-sm text-muted-foreground" title={b.staff.name}>
                              {b.staff.name}
                            </span>
                          ) : null}
                          <BookingStatus booking={b} />
                          <span className="w-28 min-w-0 shrink-0 truncate text-xs text-muted-foreground">{originLabel(b)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
