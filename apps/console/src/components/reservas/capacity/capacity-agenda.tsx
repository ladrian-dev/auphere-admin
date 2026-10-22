"use client";

import { ErrorState, Metric, formatNumber } from "@nexus/ui";

import { useReservas, useWords } from "../context";
import { periodRange } from "../model/dates";
import { counts, currentSlotTime, peakSlot, slotAt } from "../model/occupancy";
import { isListed } from "../model/waitlist";
import { Toolbar } from "../toolbar";
import { CapacityList } from "./capacity-list";
import { OccupancyMap } from "./occupancy-map";

/**
 * The Ocupación tab of Aforo (spec 043, T024): four figures, then the map
 * (Cuadrícula) or the list of the day by hour (Lista).
 */
export function CapacityAgenda() {
  const { t, data, url, refresh } = useReservas();
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Toolbar />
      <Figures />
      {url.view === "list" ? (
        data.bookings === null ? (
          <ErrorState title={t("reservas.error.title")} description={t("reservas.error.body")} onRetry={refresh} retryLabel={t("common.retry")} />
        ) : (
          <CapacityList />
        )
      ) : data.occupancy === null ? (
        <ErrorState title={t("reservas.error.title")} description={t("reservas.error.body")} onRetry={refresh} retryLabel={t("common.retry")} />
      ) : (
        <OccupancyMap occupancy={data.occupancy} />
      )}
    </div>
  );
}

/** Figures of the period. On today's day: who is inside now. On another day: the peak. */
function Figures() {
  const { t, locale, data, bookings, url, today, nowMinutes, settings } = useReservas();
  const words = useWords();
  const n = (v: number) => formatNumber(v, locale);
  const range = periodRange(url.period, url.date);
  const inRange = bookings.filter((b) => b.local.date >= range.from && b.local.date <= range.to);
  const live = inRange.filter((b) => b.status !== "cancelled");
  const people = live.filter(counts).reduce((sum, b) => sum + b.party_size, 0);
  const agentPct = live.length ? Math.round((live.filter((b) => b.origin === "agent").length / live.length) * 100) : 0;
  const pending = live.filter((b) => b.status === "pending").length;
  const waiting = data.waitlist?.items.filter((w) => isListed(w) && w.status === "waiting").length ?? null;
  const seats = data.occupancy?.seats ?? settings.capacity?.seats ?? 0;
  const day = url.period === "day" ? data.occupancy?.days.find((d) => d.date === url.date) : undefined;
  const step = settings.capacity?.schedule.step_minutes ?? 30;
  const nowSlot = day && url.date === today ? currentSlotTime(day.slots.map((s) => s.time), nowMinutes, step) : null;
  const inside = nowSlot ? (slotAt(day, nowSlot)?.present ?? null) : null;
  const peak = day && url.date !== today ? peakSlot(day) : null;

  return (
    <section aria-label={t("reservas.kpi.label")} className="@container min-w-0">
      <div className="grid grid-cols-2 gap-4 @2xl:grid-cols-4">
        {inside !== null ? (
          <Metric label={t("reservas.kpi.inside")} value={t("reservas.kpi.ofSeats", { count: n(inside), seats: n(seats) })} />
        ) : peak ? (
          // The hour is the figure; the people go under it (a long «21:00 · 32 de 36» was cut).
          <Metric label={t("reservas.kpi.peak")} value={peak.time} hint={t("reservas.kpi.peakHint", { count: n(peak.present), seats: n(seats) })} />
        ) : (
          <Metric label={t("reservas.kpi.people")} value={n(people)} hint={words.unit} />
        )}
        <Metric label={t("reservas.kpi.bookings")} value={n(live.length)} hint={live.length ? t("reservas.kpi.agentShare", { pct: agentPct }) : undefined} />
        <Metric label={t("reservas.kpi.pending")} value={n(pending)} />
        <Metric label={t("reservas.kpi.waitlist")} value={waiting === null ? "—" : n(waiting)} />
      </div>
    </section>
  );
}
