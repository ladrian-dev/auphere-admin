"use client";

import * as React from "react";

import { Button, Eyebrow, Meter, Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@nexus/ui";

import { offerWaitlistAction, removeBlockAction } from "@/app/(console)/reservas/actions";

import { useReservas, useWords } from "../context";
import { dayLabel } from "../model/dates";
import { hourState, slotAt } from "../model/occupancy";
import { isListed } from "../model/waitlist";
import { useWrite } from "../shared";
import { ArrivalRow } from "./capacity-list";
import { WaitlistStatus } from "./waitlist-status";

const FIRST = 6;

/**
 * The hour panel of Aforo (spec 043, T024): «20:30 · 40 de 64 comensales»,
 * the sentence of the hour, «Reservar a esta hora» and «Bloquear» or
 * «Desbloquear», who arrives, who counts from before, and who waits for it.
 */
export function HourPanel({ date, time, onClose }: { date: string; time: string; onClose: () => void }) {
  const { t, locale, data, bookings, open } = useReservas();
  const words = useWords();
  const write = useWrite();
  const [all, setAll] = React.useState(false);
  const occupancy = data.occupancy;
  const day = occupancy?.days.find((d) => d.date === date);
  const slot = slotAt(day, time);
  const seats = occupancy?.seats ?? 0;
  const hold = occupancy?.walkin_hold ?? 0;
  const state = hourState(day, slot, seats, hold);
  const arrivals = bookings.filter((b) => b.local.date === date && b.local.start === time && b.status !== "cancelled");
  const earlier = slot ? Math.max(0, slot.present - slot.arriving) : 0;
  const waiting = (data.waitlist?.items ?? []).filter((w) => isListed(w) && w.desired.date === date && w.desired.time === time);
  const shown = all ? arrivals : arrivals.slice(0, FIRST);

  const sentence =
    state.kind === "open"
      ? hold > 0
        ? t("reservas.hour.open", { left: state.left, hold })
        : t("reservas.hour.open.noHold", { left: state.left })
      : state.kind === "full"
        ? t("reservas.hour.full")
        : state.kind === "blocked"
          ? t("reservas.hour.blocked", { label: state.label })
          : state.kind === "past"
            ? t("reservas.hour.past")
            : t("reservas.hour.closed");

  return (
    <Sheet open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-sm">
        <SheetHeader className="pr-12">
          <Eyebrow>{slot?.shift ? t("reservas.hour.eyebrow", { day: dayLabel(date, locale), shift: slot.shift }) : dayLabel(date, locale)}</Eyebrow>
          <SheetTitle className="text-balance">
            {t("reservas.hour.title", { time, present: slot?.present ?? 0, seats, unit: words.unit })}
          </SheetTitle>
          <SheetDescription>{sentence}</SheetDescription>
        </SheetHeader>
        <div className="flex min-w-0 flex-col gap-6 px-4 pb-6">
          {slot ? (
            <Meter
              value={slot.present}
              max={seats}
              label={t("reservas.hour.meter", { time })}
              labelHidden
              valueLabel={t("reservas.kpi.ofSeats", { count: slot.present, seats })}
              thresholds={{ warning: 85, danger: 100 }}
            />
          ) : null}

          {state.kind !== "closed" && state.kind !== "past" ? (
            <div className="flex flex-wrap gap-2">
              {state.kind !== "blocked" ? (
                <Button size="sm" onClick={() => open({ kind: "new", prefill: { date, time } })}>
                  {t("reservas.hour.book")}
                </Button>
              ) : null}
              {state.kind === "blocked" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void write(() => removeBlockAction({ id: state.blockId }), { success: t("reservas.hour.unblocked") }).then((r) => r.ok && onClose())}
                >
                  {t("reservas.hour.unblock")}
                </Button>
              ) : (
                <Button size="sm" variant="outline" onClick={() => open({ kind: "block", prefill: { date, from: time, until: time } })}>
                  {t("reservas.hour.block")}
                </Button>
              )}
            </div>
          ) : null}

          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("reservas.hour.arrivals", { time, bookings: words.bookings(arrivals.length) })}</h3>
            {arrivals.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("reservas.hour.arrivals.empty")}</p>
            ) : (
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
                {shown.map((b) => (
                  <ArrivalRow key={b.id} booking={b} compact />
                ))}
              </ul>
            )}
            {!all && arrivals.length > FIRST ? (
              <Button variant="link" size="sm" className="w-fit px-0" onClick={() => setAll(true)}>
                {t("reservas.hour.showAll", { count: arrivals.length })}
              </Button>
            ) : null}
            {earlier > 0 ? <p className="text-xs text-muted-foreground text-pretty">{t("reservas.hour.inside", { count: earlier, unit: words.unitFor(earlier) })}</p> : null}
          </section>

          {data.waitlist?.enabled ? (
            <section className="flex flex-col gap-2 rounded-md bg-muted p-3">
              <h3 className="text-sm font-medium">{t("reservas.hour.waitlist", { count: waiting.length })}</h3>
              <p className="text-xs text-muted-foreground text-pretty">{t("reservas.hour.waitlist.rule")}</p>
              {waiting.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("reservas.hour.waitlist.empty")}</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {waiting.map((w) => (
                    <li key={w.id} className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                      <span className="min-w-0 flex-1 truncate font-medium">{w.contact.name}</span>
                      <span className="shrink-0 text-muted-foreground">{words.people(w.party_size)}</span>
                      <WaitlistStatus
                        entry={w}
                        onOffer={() => void write(() => offerWaitlistAction({ id: w.id }), { success: t("reservas.wl.offer.done") })}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
