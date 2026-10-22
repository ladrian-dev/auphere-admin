"use client";

import * as React from "react";

import { Button, EmptyState, cn } from "@nexus/ui";

import { offerWaitlistAction, removeBlockAction } from "@/app/(console)/reservas/actions";
import type { Booking, BookingTransition } from "@/lib/backend/reservas";

import { useTransitionAction } from "../booking-detail";
import { useReservas, useWords } from "../context";
import { capitalize, dayLabel, daysBetween, instantLocal, periodRange } from "../model/dates";
import { currentSlotTime, groupByArrival, slotAt } from "../model/occupancy";
import { actionButtons, channelKey } from "../model/vocab";
import { isListed } from "../model/waitlist";
import { AgentMark, BookingStatus, useWrite } from "../shared";
import { WaitlistStatus } from "./waitlist-status";
import { WalkinBox } from "./walkin";

const INLINE: readonly BookingTransition[] = ["arrive", "noshow", "request_confirmation", "undo"];

/**
 * The Lista of Aforo (spec 043, T024; design 2b): the day by arrival time,
 * with the strip of the hours to narrow it to one, and on each row the
 * actions of the service — Llegó, No vino, Pedir confirmación, Deshacer —
 * only as `allowed` brings them. Beside it, what the day needs: walk-ins,
 * who waits, the blocks.
 */
export function CapacityList() {
  const { t, locale, url, bookings, data, today } = useReservas();
  const range = periodRange(url.period, url.date);
  const days = daysBetween(range.from, range.to);
  const [only, setOnly] = React.useState<string | null>(null);
  const occupancyDays = new Map((data.occupancy?.days ?? []).map((d) => [d.date, d]));
  const inRange = bookings.filter((b) => b.local.date >= range.from && b.local.date <= range.to);
  const withBookings = days.filter((d) => inRange.some((b) => b.local.date === d && b.status !== "cancelled"));
  const single = url.period === "day";

  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="flex min-w-0 flex-col gap-4">
        {single ? <Strip date={url.date} only={only} onOnly={setOnly} /> : null}
        {single ? (
          <DayGroups date={url.date} only={only} closed={!!occupancyDays.get(url.date)?.closed} />
        ) : withBookings.length === 0 ? (
          <EmptyState title={t("reservas.alist.empty")} readonly />
        ) : (
          withBookings.map((d) => (
            <section key={d} aria-label={capitalize(dayLabel(d, locale))} className="flex min-w-0 flex-col gap-3">
              <DayHeading date={d} />
              <DayGroups date={d} only={null} closed={false} />
            </section>
          ))
        )}
      </div>
      <aside aria-label={t("reservas.alist.rail")} className="flex min-w-0 flex-col gap-4">
        {today >= range.from && today <= range.to ? <WalkinBox /> : null}
        <PeriodWaitlist from={range.from} to={range.to} />
        <DayBlocks />
      </aside>
    </div>
  );
}

function DayHeading({ date }: { date: string }) {
  const { locale, today, t } = useReservas();
  return (
    <h3 className="text-sm font-medium">
      {capitalize(dayLabel(date, locale))}
      {date === today ? <span className="ml-2 rounded-full bg-accent px-2 text-xs text-accent-foreground">{t("reservas.toolbar.today.day")}</span> : null}
    </h3>
  );
}

/** The bars of the day's hours: how full each one is, «ahora» on the current one, a click narrows the list. */
function Strip({ date, only, onOnly }: { date: string; only: string | null; onOnly: (time: string | null) => void }) {
  const { t, data, today, nowMinutes, settings } = useReservas();
  const day = data.occupancy?.days.find((d) => d.date === date);
  if (!day || day.closed || day.slots.length === 0) return null;
  const seats = data.occupancy?.seats ?? 1;
  const step = settings.capacity?.schedule.step_minutes ?? 30;
  const now = date === today ? currentSlotTime(day.slots.map((s) => s.time), nowMinutes, step) : null;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <h3 className="text-sm font-medium">{t("reservas.alist.strip")}</h3>
        {only ? (
          <span className="inline-flex items-center gap-2 text-sm">
            <span className="rounded-full bg-accent px-2 text-accent-foreground">{t("reservas.alist.only", { time: only })}</span>
            <Button variant="link" size="sm" className="px-0" onClick={() => onOnly(null)}>
              {t("reservas.alist.all")}
            </Button>
          </span>
        ) : null}
      </div>
      <div className="min-w-0 overflow-x-auto">
        <div className="flex min-w-max items-end gap-1">
          {day.slots.map((s) => {
            const pct = Math.min(100, Math.round((s.present / seats) * 100));
            return (
              <button
                key={s.time}
                type="button"
                aria-pressed={only === s.time}
                aria-label={t("reservas.alist.strip.aria", { time: s.time, present: s.present, seats })}
                onClick={() => onOnly(only === s.time ? null : s.time)}
                className={cn(
                  "flex w-12 flex-col items-center gap-1 rounded-sm p-1 text-xs tabular-nums",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring hover:bg-muted",
                  only === s.time && "bg-accent text-accent-foreground",
                  s.past && "opacity-60",
                )}
              >
                <span aria-hidden="true" className="flex h-12 w-4 items-end overflow-hidden rounded-sm bg-muted">
                  <span className={cn("block w-full rounded-sm", s.blocked ? "bg-muted-foreground/40" : pct >= 85 ? "bg-primary-deep" : "bg-primary")} style={{ height: `${pct}%` }} />
                </span>
                <span>{s.time}</span>
                {now === s.time ? <span className="font-medium text-primary-text">{t("reservas.alist.now")}</span> : null}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DayGroups({ date, only, closed }: { date: string; only: string | null; closed: boolean }) {
  const { t, bookings, data, today, nowMinutes, settings } = useReservas();
  const words = useWords();
  const day = data.occupancy?.days.find((d) => d.date === date);
  const seats = data.occupancy?.seats ?? settings.capacity?.seats ?? 0;
  const step = settings.capacity?.schedule.step_minutes ?? 30;
  const now = date === today && day ? currentSlotTime(day.slots.map((s) => s.time), nowMinutes, step) : null;
  const groups = groupByArrival(bookings.filter((b) => b.local.date === date)).filter((g) => !only || g.time === only);

  if (closed) return <EmptyState title={t("reservas.alist.closedDay")} readonly />;
  if (groups.length === 0) return <EmptyState title={t("reservas.alist.emptyDay")} readonly />;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {groups.map((g) => {
        const slot = slotAt(day, g.time);
        const pct = slot && seats ? Math.min(100, Math.round((slot.present / seats) * 100)) : 0;
        return (
          <section key={g.time} aria-label={g.time} className="flex min-w-0 flex-col gap-2">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-base font-semibold tabular-nums">{g.time}</span>
              {now === g.time ? <span className="rounded-full bg-primary px-2 text-xs font-medium text-primary-foreground">{t("reservas.alist.now")}</span> : null}
              <span className="min-w-0 text-sm text-muted-foreground">
                {t("reservas.alist.group", { bookings: words.bookings(g.bookings.length), people: words.people(g.people) })}
              </span>
              {slot ? (
                <span className="ml-auto inline-flex items-center gap-2 text-xs text-muted-foreground tabular-nums">
                  {t("reservas.kpi.ofSeats", { count: slot.present, seats })}
                  <span aria-hidden="true" className="h-1 w-16 overflow-hidden rounded-full bg-muted">
                    <span className={cn("block h-full", pct >= 85 ? "bg-primary-deep" : "bg-primary")} style={{ width: `${pct}%` }} />
                  </span>
                </span>
              ) : null}
            </div>
            {slot?.blocked ? <p className="text-xs text-muted-foreground">{t("reservas.alist.blocked", { label: slot.blocked.label })}</p> : null}
            <ul className="flex min-w-0 flex-col divide-y divide-border rounded-md border border-border bg-card">
              {g.bookings.map((b) => (
                <ArrivalRow key={b.id} booking={b} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

/** One booking of an hour: people, name, channel and note (or when they arrived), status, inline actions. */
export function ArrivalRow({ booking: b, compact = false }: { booking: Booking; compact?: boolean }) {
  const { t, mode, settings, open } = useReservas();
  const transition = useTransitionAction();
  const name = b.contact.name ?? t("reservas.detail.walkinName");
  const arrived = b.arrived_at ? instantLocal(b.arrived_at, settings.timezone).time : null;
  const meta = arrived
    ? `${t("reservas.alist.arrivedAt", { time: arrived })} · ${t(channelKey(b.channel))}`
    : [t(channelKey(b.channel)), b.note].filter(Boolean).join(" · ");
  const inline = compact ? [] : actionButtons(b.allowed, mode, INLINE);
  return (
    <li className={cn("flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2", b.status === "cancelled" && "text-muted-foreground")}>
      <span className="w-8 shrink-0 text-center text-base font-semibold tabular-nums">{b.party_size}</span>
      <button
        type="button"
        onClick={() => open({ kind: "detail", id: b.id, booking: b })}
        className="flex min-w-0 flex-1 basis-40 flex-col rounded-sm text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <span className="flex min-w-0 items-center gap-1 text-sm font-medium">
          <span className="truncate hover:underline" title={name}>
            {name}
          </span>
          {b.origin === "agent" ? <AgentMark /> : null}
        </span>
        <span className="truncate text-xs text-muted-foreground" title={meta}>
          {meta}
        </span>
      </button>
      <span className="flex max-w-full shrink-0 flex-wrap items-center gap-2">
        {b.late_minutes ? <span className="text-xs font-medium text-warning">{t("reservas.detail.late", { minutes: b.late_minutes })}</span> : null}
        <BookingStatus booking={b} />
        {inline.map((btn) => (
          <Button
            key={btn.action}
            size="xs"
            variant={btn.action === "arrive" ? "default" : "outline"}
            aria-label={t("reservas.action.aria", { action: t(btn.labelKey), name })}
            onClick={() => void transition(b, btn.action as BookingTransition)}
          >
            {t(btn.labelKey)}
          </Button>
        ))}
      </span>
    </li>
  );
}

function PeriodWaitlist({ from, to }: { from: string; to: string }) {
  const { t, data } = useReservas();
  const words = useWords();
  const write = useWrite();
  if (!data.waitlist?.enabled) return null;
  const items = data.waitlist.items.filter((w) => isListed(w) && w.desired.date && w.desired.date >= from && w.desired.date <= to);
  return (
    <section className="flex flex-col gap-2 rounded-md border border-border bg-card p-4">
      <h3 className="text-sm font-medium">{t("reservas.wl.period.title")}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.wl.period.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((w) => (
            <li key={w.id} className="flex min-w-0 flex-col gap-1 text-sm">
              <span className="flex min-w-0 items-center justify-between gap-2">
                <span className="truncate font-medium">{w.contact.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {words.dayTitle(w.desired.date!)} · {w.desired.time}
                </span>
              </span>
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">{words.people(w.party_size)}</span>
                <WaitlistStatus entry={w} onOffer={() => void write(() => offerWaitlistAction({ id: w.id }), { success: t("reservas.wl.offer.done") })} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DayBlocks() {
  const { t, data, url, open } = useReservas();
  const write = useWrite();
  const range = periodRange(url.period, url.date);
  const items = (data.blocks ?? []).filter((b) => (url.period === "day" ? b.date === url.date : b.date >= range.from && b.date <= range.to));
  const words = useWords();
  return (
    <section className="flex flex-col gap-2 rounded-md border border-border bg-card p-4">
      <h3 className="text-sm font-medium">{t("reservas.blocks.day")}</h3>
      {data.blocks === null ? (
        <p className="text-sm text-muted-foreground">{t("reservas.settings.partError")}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.blocks.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((b) => (
            <li key={b.id} className="flex min-w-0 items-center gap-2 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block truncate" title={b.label}>
                  {url.period === "day" ? "" : `${words.dayTitle(b.date)} · `}
                  {t("reservas.blocks.item", { from: b.from, until: b.until, label: b.label })}
                </span>
              </span>
              <Button
                size="xs"
                variant="ghost"
                aria-label={t("reservas.blocks.remove.aria", { label: b.label })}
                onClick={() => void write(() => removeBlockAction({ id: b.id }), { success: t("reservas.blocks.removed") })}
              >
                {t("reservas.blocks.remove")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Button size="sm" variant="outline" className="w-fit" onClick={() => open({ kind: "block", prefill: { date: url.date } })}>
        {t("reservas.blocks.add")}
      </Button>
    </section>
  );
}
