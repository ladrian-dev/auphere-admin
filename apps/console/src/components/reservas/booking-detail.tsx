"use client";

import { AlertTriangle, Clock, MessageCircle, Phone, StickyNote, UserRound } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, ErrorState, Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, Skeleton, cn } from "@nexus/ui";

import { bookingDetailAction, bookingTransitionAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { Booking, BookingAction, BookingDetail, BookingTransition } from "@/lib/backend/reservas";

import { useReservas, useWords } from "./context";
import { formatMinutes } from "./model/dates";
import { bookingSpan } from "./model/day-grid";
import { eventLine, originLine } from "./model/events";
import { formatPrice } from "./model/money";
import { useActionLoad } from "./model/use-load";
import { actionButtons, channelKey } from "./model/vocab";
import { BookingStatus, Initials, useWrite } from "./shared";

/** The status a transition leaves, painted before the API answers (it is reverted if it says no). */
export const OPTIMISTIC_STATUS: Partial<Record<BookingTransition, Booking["status"]>> = {
  confirm: "confirmed",
  arrive: "arrived",
  noshow: "noshow",
  undo: "confirmed",
};

/** Run a state transition from `allowed`, optimistic, told by `useWrite`. Resolves with whether it went through. */
export function useTransitionAction() {
  const { t, touch } = useReservas();
  const write = useWrite();
  return React.useCallback(
    async (b: Booking, action: BookingTransition): Promise<boolean> => {
      // An urgent update, not a transition: it paints now, while the API answers.
      const status = OPTIMISTIC_STATUS[action];
      if (status) touch(b.id, { status, allowed: [] });
      const res = await write(() => bookingTransitionAction({ id: b.id, version: b.version, action }), {
        success: t(`reservas.done.${action}` as MessageKey),
      });
      // Refused: the mark goes and the booking shows what is true (a new read follows on 409/412).
      if (!res.ok && status) touch(b.id, null);
      return res.ok;
    },
    [t, touch, write],
  );
}

/**
 * The side panel of a booking (spec 043, T023/T024): who, when, with whom,
 * how to reach them, its status, where it came from and its history — written
 * from `events[]`, never raw — and **only** the buttons `allowed` brings.
 */
export function BookingDetailSheet({ id, initial, onClose }: { id: string; initial: Booking | null; onClose: () => void }) {
  const { t } = useReservas();
  // Each read has its own key: «Reintentar» and the quiet read after a change ask again;
  // the quiet one keeps the booking on screen meanwhile instead of a skeleton.
  const [round, setRound] = React.useState(0);
  const state = useActionLoad<BookingDetail>(`${id}|${round}`, () => bookingDetailAction({ id }), { keepOk: true });
  const load = () => setRound((n) => n + 1);

  const name = (state.kind === "ok" ? state.data.contact.name : initial?.contact.name) ?? t("reservas.detail.walkinName");

  return (
    <Sheet open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-sm">
        <SheetHeader className="pr-12">
          <SheetTitle className="text-balance">{t("reservas.detail.title", { name })}</SheetTitle>
          <SheetDescription className="sr-only">{t("reservas.detail.history")}</SheetDescription>
        </SheetHeader>
        <div className="flex min-w-0 flex-col gap-6 px-4 pb-6">
          {state.kind === "ok" ? (
            <DetailBody detail={state.data} onChanged={load} />
          ) : state.kind === "error" ? (
            <ErrorState title={t("reservas.detail.error")} onRetry={load} retryLabel={t("common.retry")} />
          ) : (
            <DetailSkeleton label={t("reservas.detail.loading")} />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function DetailSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Skeleton className="size-10 rounded-full" />
        <div className="flex flex-1 flex-col gap-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <Skeleton className="h-6 w-28 rounded-full" />
      <Skeleton className="h-16 w-full" />
      <div className="flex gap-2">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-24" />
      </div>
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

function DetailBody({ detail: b, onChanged }: { detail: BookingDetail; onChanged: () => void }) {
  const { t, locale, mode, settings, hasInbox, open } = useReservas();
  const words = useWords();
  const transition = useTransitionAction();
  const name = b.contact.name ?? t("reservas.detail.walkinName");
  const span = bookingSpan(b);
  const price = formatPrice(b.price, locale);
  const sub =
    mode === "services"
      ? [b.service?.name, b.service ? formatMinutes(b.service.duration_minutes) : null, price].filter(Boolean).join(" · ")
      : `${words.people(b.party_size)} · ${words.dayTitle(b.local.date)}`;
  const buttons = actionButtons(b.allowed, mode);
  const channel = (c: string) => t(channelKey(c as Booking["channel"]));
  const origin = originLine(b, { agent: t("reservas.actor.agent"), when: words.instant(b.created_at), channel });

  const onAction = (action: BookingAction) => {
    if (action === "move") return open({ kind: "move", booking: b });
    if (action === "cancel") return open({ kind: "cancel", booking: b });
    // The panel reads the booking again once the change is in (or refused: it shows what is true now).
    void transition(b, action).then(onChanged);
  };

  return (
    <>
      <div className="flex min-w-0 items-center gap-3">
        <Initials name={b.contact.name} className="size-10 text-sm" />
        <div className="flex min-w-0 flex-col">
          <p className="truncate text-base font-medium" title={name}>
            {name}
          </p>
          <p className="truncate text-sm text-muted-foreground">{sub}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <BookingStatus booking={b} />
        {b.late_minutes ? (
          <span className="text-sm font-medium text-warning">{t("reservas.detail.late", { minutes: b.late_minutes })}</span>
        ) : null}
      </div>

      {b.clash && b.staff ? (
        <p role="note" className="flex gap-2 rounded-md border border-status-warning-border bg-status-warning-bg px-3 py-2 text-sm text-pretty">
          <AlertTriangle className="mt-1 size-4 shrink-0 text-warning" aria-hidden="true" />
          {t("reservas.detail.clash", { name: b.staff.name, from: b.clash.local.start, to: b.clash.local.end })}
        </p>
      ) : null}

      <dl className="grid min-w-0 grid-cols-[auto_1fr] items-start gap-x-3 gap-y-3 text-sm">
        <dt>
          <Clock className="mt-1 size-4 text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">{t("reservas.detail.when")}</span>
        </dt>
        <dd className="min-w-0">
          {t("reservas.when.span", { day: words.dayTitle(b.local.date), from: b.local.start, to: b.local.end })}
          <span className="text-muted-foreground"> · {formatMinutes(span.to - span.from)}</span>
        </dd>
        {b.staff ? (
          <>
            <dt>
              <UserRound className="mt-1 size-4 text-muted-foreground" aria-hidden="true" />
              <span className="sr-only">{t("reservas.form.staff")}</span>
            </dt>
            <dd className="min-w-0">
              {t("reservas.detail.with", { name: b.staff.name })}
              {b.any_staff ? <span className="block text-xs text-muted-foreground">{t("reservas.detail.anyStaff")}</span> : null}
            </dd>
          </>
        ) : null}
        <dt>
          <Phone className="mt-1 size-4 text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">{t("reservas.detail.contact")}</span>
        </dt>
        <dd className="flex min-w-0 flex-col gap-1">
          <span className="break-words">
            {b.contact.phone ? `${channel(b.channel)} · ${b.contact.phone}` : t("reservas.detail.noPhone")}
          </span>
          {hasInbox && b.contact.conversation_id ? (
            <Link
              href={`/inbox?c=${encodeURIComponent(b.contact.conversation_id)}`}
              className="inline-flex w-fit items-center gap-1 text-primary-text underline-offset-4 hover:underline"
            >
              <MessageCircle className="size-4" aria-hidden="true" />
              {t("reservas.detail.openChat")}
            </Link>
          ) : null}
        </dd>
        {b.note ? (
          <>
            <dt>
              <StickyNote className="mt-1 size-4 text-muted-foreground" aria-hidden="true" />
              <span className="sr-only">{t("reservas.detail.note")}</span>
            </dt>
            <dd className="min-w-0 break-words text-pretty">{b.note}</dd>
          </>
        ) : null}
      </dl>

      {b.wants_earlier && settings.waitlist.enabled ? (
        <p className="rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground">{t("reservas.detail.wantsEarlier")}</p>
      ) : null}

      <section aria-label={t("reservas.detail.actions")} className="flex flex-col gap-2">
        {buttons.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("reservas.detail.noActions")}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {buttons.map((btn) => (
              <Button
                key={btn.action}
                size="sm"
                variant={btn.destructive ? "destructive" : btn.action === "confirm" || btn.action === "arrive" ? "default" : "outline"}
                onClick={() => onAction(btn.action)}
              >
                {t(btn.labelKey)}
              </Button>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{t("reservas.detail.origin")}</h3>
        <p className="text-sm text-pretty">{t(origin.key, origin.vars)}</p>
      </section>

      <History detail={b} />
    </>
  );
}

function History({ detail: b }: { detail: BookingDetail }) {
  const { t, mode } = useReservas();
  const words = useWords();
  const ctx = {
    mode,
    contact: b.contact.name ?? t("reservas.detail.walkinName"),
    agent: t("reservas.actor.agent"),
    system: t("reservas.actor.system"),
    when: (at: { date?: unknown; start?: unknown; time?: unknown }) => {
      const date = typeof at.date === "string" ? at.date : b.local.date;
      const time = typeof at.start === "string" ? at.start : typeof at.time === "string" ? at.time : "";
      return time ? words.at(date, time) : words.day(date);
    },
    why: (w: string) => t(`reservas.why.${WHY.has(w) ? w : "send_failed"}` as MessageKey),
    channel: (c: string) => t(channelKey(c as Booking["channel"])),
  };
  const events = [...b.events].sort((x, y) => y.at.localeCompare(x.at));
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{t("reservas.detail.history")}</h3>
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.detail.history.empty")}</p>
      ) : (
        <ol className="flex flex-col gap-3 border-l border-border pl-4">
          {events.map((ev, i) => {
            const line = eventLine(ev, ctx);
            return (
              <li key={`${ev.kind}-${ev.at}-${i}`} className={cn("relative flex flex-col text-sm", ev.kind === "notify_failed" && "text-destructive")}>
                <span aria-hidden="true" className="absolute top-2 -left-5 size-2 rounded-full bg-border" />
                <span className="text-pretty">{t(line.key, line.vars)}</span>
                <span className="text-xs text-muted-foreground">{words.instant(ev.at)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/** `notify_failed.data.why` of the contract; anything else reads as «the send failed». */
const WHY = new Set(["no_phone", "no_template", "opted_out", "no_channel", "send_failed"]);
