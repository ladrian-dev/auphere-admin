"use client";

import { ListPlus, UserPlus } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Section,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@nexus/ui";

import { offerWaitlistAction, patchSettingsAction, removeWaitlistAction, stopOfferAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { SlotOffer, WaitlistEntry } from "@/lib/backend/reservas";

import { WaitlistStatus } from "../capacity/waitlist-status";
import { useReservas, useWords } from "../context";
import { diffDays, formatMinutes, weekdayDay } from "../model/dates";
import { countdown, isListed, offerState } from "../model/waitlist";
import { useWrite } from "../shared";
import { AddWaitlistDialog } from "./add-waitlist-dialog";

/** A clock that ticks every second, only while something counts down. */
function useTick(active: boolean, start: Date): Date {
  const [now, setNow] = React.useState(start);
  React.useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

/**
 * The Lista de espera tab (spec 043, T025), both modes. Off, it says what it
 * would do and turns on with its rules in view. On: in Servicios, the slots
 * being offered right now (who has the turn, with a live countdown) and the
 * people on the list; in Aforo, who waits for room, with «Ofrecer».
 */
export function WaitlistTab() {
  const { t, data, mode, refresh } = useReservas();
  if (data.waitlist === null) {
    return <ErrorState title={t("reservas.error.title")} description={t("reservas.error.body")} onRetry={refresh} retryLabel={t("common.retry")} />;
  }
  if (!data.waitlist.enabled) return <WaitlistOff />;
  return mode === "services" ? <ServicesWaitlist /> : <CapacityWaitlist />;
}

function WaitlistOff() {
  const { t, mode, settings } = useReservas();
  const write = useWrite();
  const [asking, setAsking] = React.useState(false);
  const lead = formatMinutes(settings.waitlist.lead_minutes);
  return (
    <>
      <EmptyState
        icon={ListPlus}
        title={t("reservas.wl.off.title")}
        description={t(mode === "services" ? "reservas.wl.off.body.services" : "reservas.wl.off.body.capacity")}
        action={<Button onClick={() => setAsking(true)}>{t("reservas.wl.activate")}</Button>}
      />
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={t("reservas.wl.activate.title")}
        description={t(mode === "services" ? "reservas.wl.activate.rules.services" : "reservas.wl.activate.rules.capacity", { lead })}
        confirmLabel={t("reservas.wl.activate")}
        cancelLabel={t("common.cancel")}
        onConfirm={async () => {
          const res = await write(() => patchSettingsAction({ version: settings.version, patch: { waitlist: { enabled: true } } }), {
            success: t("reservas.wl.activated"),
          });
          if (res.ok) setAsking(false);
        }}
      />
    </>
  );
}

function joinedLine(w: WaitlistEntry, t: ReturnType<typeof useReservas>["t"], when: string): string {
  if (w.joined.kind === "agent") return t("reservas.wl.joined.agent", { when });
  // `in_person`: the team put them on the list at the door — a person, with their name.
  if ((w.joined.kind === "person" || w.joined.kind === "in_person") && w.joined.name) return t("reservas.wl.joined.person", { name: w.joined.name, when });
  return t("reservas.wl.joined.system", { when });
}

/**
 * What a Servicios entry wants: an earlier time for its booking — which one,
 * from `booking_local` (enmienda 2026-10-22): «de mañana a las 10:00», «del
 * jueves 29 a las 12:00» —, any opening until a day, or a given day.
 */
function useWants() {
  const { t, locale, today } = useReservas();
  const words = useWords();
  return (w: WaitlistEntry): string => {
    if (w.booking_id) {
      const at = w.booking_local;
      if (!at) return t("reservas.wl.wants.earlier");
      const near = diffDays(today, at.date);
      return near === 0 || near === 1
        ? t("reservas.wl.wants.earlierRel", { day: words.day(at.date), time: at.start })
        : t("reservas.wl.wants.earlierOn", { day: weekdayDay(at.date, locale), time: at.start });
    }
    if (w.desired.until) return t("reservas.wl.wants.until", { day: words.day(w.desired.until) });
    if (w.desired.date) return words.dayTitle(w.desired.date);
    return t("reservas.wl.wants.any");
  };
}

function ServicesWaitlist() {
  const { t, data } = useReservas();
  const words = useWords();
  const write = useWrite();
  const wants = useWants();
  const [adding, setAdding] = React.useState(false);
  // `recent` also brings what still runs: each offer once.
  const running = data.offers?.running ?? [];
  const offers = data.offers ? [...running, ...data.offers.recent.filter((o) => !running.some((r) => r.id === o.id))] : null;
  const people = (data.waitlist?.items ?? []).filter(isListed);

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Section title={t("reservas.wl.offers.title")}>
        {offers === null ? (
          <p className="text-sm text-muted-foreground">{t("reservas.settings.partError")}</p>
        ) : offers.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("reservas.wl.offers.empty")}</p>
        ) : (
          <ul className="grid min-w-0 gap-4 xl:grid-cols-2">
            {offers.map((o) => (
              <OfferCard key={o.id} offer={o} />
            ))}
          </ul>
        )}
      </Section>

      <Section
        title={t("reservas.wl.people.title")}
        padded={false}
        actions={
          <Button size="sm" variant="outline" onClick={() => setAdding(true)} disabled={!data.services?.length}>
            <UserPlus aria-hidden="true" />
            {t("reservas.wl.add.open")}
          </Button>
        }
      >
        {people.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-muted-foreground">{t("reservas.wl.people.empty")}</p>
        ) : (
          <Table className="min-w-176">
            <TableHeader>
              <TableRow>
                <TableHead>{t("reservas.wl.col.person")}</TableHead>
                <TableHead>{t("reservas.wl.col.wants")}</TableHead>
                <TableHead>{t("reservas.wl.col.service")}</TableHead>
                <TableHead>{t("reservas.wl.col.with")}</TableHead>
                <TableHead>{t("reservas.wl.col.joined")}</TableHead>
                <TableHead className="sr-only">{t("reservas.wl.col.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {people.map((w) => (
                <TableRow key={w.id}>
                  <TableCell className="max-w-48">
                    <span className="block truncate font-medium" title={w.contact.name ?? undefined}>
                      {w.contact.name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">{w.contact.phone ?? t("reservas.wl.noPhone")}</span>
                  </TableCell>
                  <TableCell className="max-w-56 text-pretty">{wants(w)}</TableCell>
                  <TableCell>
                    {w.service ? (
                      <>
                        <span className="block">{w.service.name}</span>
                        <span className="block text-xs text-muted-foreground">{formatMinutes(w.service.duration_minutes)}</span>
                      </>
                    ) : null}
                  </TableCell>
                  <TableCell>{w.staff?.name ?? t("reservas.wl.with.any")}</TableCell>
                  <TableCell className="text-muted-foreground">{joinedLine(w, t, words.instant(w.joined.at))}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="xs"
                      variant="ghost"
                      aria-label={t("reservas.wl.remove.aria", { name: w.contact.name ?? "" })}
                      onClick={() => void write(() => removeWaitlistAction({ id: w.id }), { success: t("reservas.wl.removed") })}
                    >
                      {t("reservas.wl.remove")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      {adding ? <AddWaitlistDialog onClose={() => setAdding(false)} /> : null}
    </div>
  );
}

const STATE_TONE = { running: "info", filled: "positive", stopped: "muted", nobody: "muted" } as const;

export function OfferCard({ offer }: { offer: SlotOffer }) {
  const { t, href, now: start } = useReservas();
  const words = useWords();
  const write = useWrite();
  const state = offerState(offer);
  const now = useTick(state.kind === "running", start);
  const left = state.kind === "running" ? countdown(state.current?.deadline_at, now) : null;
  const slot = offer.slot;
  const candidates = [...offer.candidates].sort((a, b) => a.position - b.position);

  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-md border border-border p-4">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{t("reservas.when.span", { day: words.dayTitle(slot.local.date), from: slot.local.start, to: slot.local.end })}</p>
          <p className="truncate text-sm text-muted-foreground">
            {offer.cancelled_by_name
              ? t("reservas.wl.offer.sub", { service: slot.service?.name ?? "", staff: slot.staff?.name ?? "", name: offer.cancelled_by_name })
              : t("reservas.wl.offer.subNoName", { service: slot.service?.name ?? "", staff: slot.staff?.name ?? "" })}
          </p>
        </div>
        <StatusBadge tone={STATE_TONE[state.kind]} pulse={state.kind === "running"}>
          {state.kind === "running"
            ? t("reservas.wl.offer.state.running", { index: state.index, total: state.total })
            : t(`reservas.wl.offer.state.${state.kind}` as MessageKey)}
        </StatusBadge>
      </div>
      {state.kind === "running" && state.current && left ? (
        <p className="text-sm text-pretty" aria-live="off">
          {t("reservas.wl.offer.turn", { name: state.current.name ?? "", time: left })}
        </p>
      ) : null}
      <ol aria-label={t("reservas.wl.candidates")} className="flex flex-col gap-1 text-sm">
        {candidates.map((c) => {
          const cLeft = c.status === "waiting" ? countdown(c.deadline_at, now) : null;
          return (
            <li key={c.waitlist_id} className="flex min-w-0 items-baseline gap-2">
              <span className="w-4 shrink-0 text-right text-xs text-muted-foreground tabular-nums">{c.position}</span>
              <span className="min-w-0 flex-1 truncate">{c.name}</span>
              <span className={cn("shrink-0 text-xs", c.status === "accepted" || c.status === "late_won" ? "text-status-positive-text" : "text-muted-foreground")}>
                {c.status === "waiting"
                  ? cLeft
                    ? t("reservas.wl.cand.waitingTime", { time: cLeft })
                    : t("reservas.wl.cand.waiting")
                  : t(`reservas.wl.cand.${c.status}` as MessageKey)}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap gap-2">
        {state.kind === "running" ? (
          <Button size="sm" variant="outline" onClick={() => void write(() => stopOfferAction({ id: offer.id }), { success: t("reservas.wl.offer.stopped") })}>
            {t("reservas.wl.offer.stop")}
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" nativeButton={false} render={<Link href={href({ tab: "agenda", view: "grid", period: "day", date: slot.local.date })} />}>
          {t("reservas.wl.offer.see")}
        </Button>
      </div>
    </li>
  );
}

function CapacityWaitlist() {
  const { t, data } = useReservas();
  const words = useWords();
  const write = useWrite();
  const people = (data.waitlist?.items ?? []).filter(isListed);
  return (
    <Section title={t("reservas.wl.capacity.title")} description={t("reservas.wl.capacity.body")} padded={false}>
      {people.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-muted-foreground">{t("reservas.wl.capacity.empty")}</p>
      ) : (
        <Table className="min-w-160">
          <TableHeader>
            <TableRow>
              <TableHead>{t("reservas.wl.col.person")}</TableHead>
              <TableHead>{t("reservas.wl.col.people")}</TableHead>
              <TableHead>{t("reservas.wl.col.wants")}</TableHead>
              <TableHead>{t("reservas.wl.col.status")}</TableHead>
              <TableHead>{t("reservas.wl.col.joined")}</TableHead>
              <TableHead className="sr-only">{t("reservas.wl.col.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {people.map((w) => (
              <TableRow key={w.id}>
                <TableCell className="max-w-48">
                  <span className="block truncate font-medium" title={w.contact.name ?? undefined}>
                    {w.contact.name}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">{w.contact.phone ?? t("reservas.wl.noPhone")}</span>
                </TableCell>
                <TableCell className="tabular-nums">{words.people(w.party_size)}</TableCell>
                <TableCell className="tabular-nums">
                  {w.desired.date ? `${words.dayTitle(w.desired.date)} · ${w.desired.time ?? ""}` : t("reservas.wl.wants.any")}
                </TableCell>
                <TableCell>
                  <WaitlistStatus entry={w} onOffer={() => void write(() => offerWaitlistAction({ id: w.id }), { success: t("reservas.wl.offer.done") })} />
                </TableCell>
                <TableCell className="text-muted-foreground">{joinedLine(w, t, words.instant(w.joined.at))}</TableCell>
                <TableCell className="text-right">
                  <Button
                    size="xs"
                    variant="ghost"
                    aria-label={t("reservas.wl.remove.aria", { name: w.contact.name ?? "" })}
                    onClick={() => void write(() => removeWaitlistAction({ id: w.id }), { success: t("reservas.wl.removed") })}
                  >
                    {t("reservas.wl.remove")}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Section>
  );
}
