"use client";

import { Plus, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Alert, AlertDescription, Button, Callout, ErrorState, PageHeader, StatusDot, cn } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { Booking } from "@/lib/backend/reservas";

import { BookingDetailSheet } from "./booking-detail";
import { CancelDialog } from "./cancel-dialog";
import { BlockDialog } from "./capacity/block-dialog";
import { CapacityAgenda } from "./capacity/capacity-agenda";
import { CapacityBookingDialog } from "./capacity/capacity-booking-dialog";
import { HourPanel } from "./capacity/hour-panel";
import { WalkinDialog } from "./capacity/walkin";
import { ReservasProvider, useReservas, useWords, type Overlay, type ReservasCtx, type ReservasData } from "./context";
import { formatMinutes, localClock } from "./model/dates";
import { reservasHref, type ReservasUrl } from "./model/url-state";
import { kindOf, stayKey } from "./model/vocab";
import { isListed } from "./model/waitlist";
import { ServicesBookingDialog } from "./services/booking-dialog";
import { ServicesAgenda } from "./services/services-agenda";
import { CapacitySettings } from "./settings/capacity-settings";
import { ServicesSettings } from "./settings/services-settings";
import { WaitlistTab } from "./waitlist/waitlist-tab";

export type ReservasInitial = {
  url: ReservasUrl;
  /** The server's clock, so «now» does not differ between server and browser on the first paint. */
  nowIso: string;
  /** `null` = the settings could not be read: without the mode there is no screen to paint. */
  data: ReservasData | null;
  /** The parts that failed (partial state). */
  errors: string[];
  hasInbox: boolean;
  /** `?booking={id}`: the booking to open on arrival (the Panel's link, T026). */
  booking?: string | null;
};

/** «Now», ticking every 30 s from the server's instant. */
function useNow(iso: string): Date {
  const [now, setNow] = React.useState(() => new Date(iso));
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

/**
 * Reservas (spec 043, T022–T025): one screen, in the mode Auphere chose for
 * the client. The URL holds where it is; the server reads what it shows;
 * writes go through Server Actions and then read again. A status change is
 * painted at once and undone if the API says no.
 */
export function ReservasView({ initial }: { initial: ReservasInitial }) {
  const t = useT();
  const router = useRouter();
  if (initial.data === null) {
    return (
      <>
        <PageHeader title={t("reservas.title")} size="compact" />
        <ErrorState title={t("reservas.error.title")} description={t("reservas.error.body")} onRetry={() => router.refresh()} retryLabel={t("common.retry")} />
      </>
    );
  }
  return <Loaded initial={initial} data={initial.data} />;
}

function Loaded({ initial, data }: { initial: ReservasInitial; data: ReservasData }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const now = useNow(initial.nowIso);
  const settings = data.settings;
  const clock = localClock(now, settings.timezone);
  // A booking on the URL opens its panel on arrival; closing it takes it off the URL,
  // so a reload or the back button does not open it again.
  const linked = initial.booking ?? null;
  const [overlay, setOverlay] = React.useState<Overlay | null>(() =>
    linked ? { kind: "detail", id: linked, booking: data.bookings?.items.find((b) => b.id === linked) ?? null } : null,
  );

  // Optimistic marks over what the server sent, tied to that read: a new read drops them.
  const base = data.bookings?.items;
  const [marked, setMarked] = React.useState<{ base: Booking[] | undefined; marks: Record<string, Partial<Booking>> }>({ base, marks: {} });
  const bookings = React.useMemo(() => {
    const marks = marked.base === base ? marked.marks : {};
    return (base ?? []).map((b) => (marks[b.id] ? { ...b, ...marks[b.id] } : b));
  }, [base, marked]);

  const ctx: ReservasCtx = React.useMemo(() => {
    const today = clock.date;
    const hrefCtx = { today, mode: settings.mode };
    return {
      data,
      settings,
      mode: settings.mode,
      kind: kindOf(settings),
      url: initial.url,
      today,
      nowMinutes: clock.minutes,
      now,
      locale,
      t,
      hasInbox: initial.hasInbox,
      bookings,
      href: (patch) => reservasHref(initial.url, patch, hrefCtx),
      go: (patch) => startTransition(() => router.push(reservasHref(initial.url, patch, hrefCtx), { scroll: false })),
      pending,
      refresh: () => startTransition(() => router.refresh()),
      open: setOverlay,
      touch: (id, patch) =>
        setMarked((m) => {
          const marks = { ...(m.base === base ? m.marks : {}) };
          if (patch) marks[id] = patch;
          else delete marks[id];
          return { base, marks };
        }),
    };
  }, [data, settings, initial.url, initial.hasInbox, clock.date, clock.minutes, now, locale, t, base, bookings, pending, router]);

  return (
    <ReservasProvider value={ctx}>
      <Header />
      {settings.hours_missing ? <HoursMissing /> : null}
      {initial.errors.length > 0 ? (
        <Alert role="status">
          <AlertDescription className="flex flex-wrap items-center gap-2">
            {t("reservas.partial")}
            <Button size="xs" variant="outline" onClick={ctx.refresh}>
              {t("common.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      <Tabs />
      <div
        aria-busy={pending || undefined}
        className={cn("min-w-0 transition-opacity duration-(--duration-state)", pending && "opacity-60")}
      >
        {initial.url.tab === "waitlist" ? (
          <WaitlistTab />
        ) : initial.url.tab === "settings" ? (
          settings.mode === "services" ? (
            <ServicesSettings />
          ) : (
            <CapacitySettings />
          )
        ) : settings.mode === "services" ? (
          <ServicesAgenda />
        ) : (
          <CapacityAgenda />
        )}
      </div>
      <Overlays
        overlay={overlay}
        close={() => {
          if (linked) router.replace(ctx.href({}), { scroll: false });
          setOverlay(null);
        }}
      />
    </ReservasProvider>
  );
}

function Header() {
  const { t, settings, mode, data, href, open } = useReservas();
  const words = useWords();
  const kind = kindOf(settings);
  const on = settings.waitlist.enabled;
  const state = t(on ? "reservas.waitlist.pill.on" : "reservas.waitlist.pill.off");
  const cannotBook = mode === "services" && (!data.staff?.length || !data.services?.length);
  const line =
    mode === "capacity" && settings.capacity
      ? t("reservas.header.capacityLine", {
          seats: settings.capacity.seats,
          unit: words.unit,
          stay: t(stayKey(kind)),
          duration: formatMinutes(settings.capacity.stay_minutes),
        })
      : undefined;
  return (
    <PageHeader
      title={t("reservas.title")}
      description={line}
      size="compact"
      actions={
        <>
          <Link
            href={href({ tab: "settings" })}
            aria-label={t("reservas.waitlist.pill.aria", { state })}
            className="inline-flex h-8 items-center gap-2 rounded-full border border-border px-3 text-sm whitespace-nowrap transition-colors duration-(--duration-hover) hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <StatusDot tone={on ? "positive" : "muted"} />
            {state}
          </Link>
          {mode === "capacity" ? (
            <Button variant="outline" onClick={() => open({ kind: "walkin" })}>
              <UserPlus aria-hidden="true" />
              {t("reservas.walkin.open")}
            </Button>
          ) : null}
          <Button onClick={() => open({ kind: "new", prefill: {} })} disabled={cannotBook}>
            <Plus aria-hidden="true" />
            {t("reservas.new")}
          </Button>
        </>
      }
    />
  );
}

function HoursMissing() {
  const { t, href } = useReservas();
  return (
    <Callout
      tone="warning"
      title={t("reservas.hoursMissing.title")}
      action={
        <Button size="sm" variant="outline" nativeButton={false} render={<Link href={href({ tab: "settings" })} />}>
          {t("reservas.hoursMissing.action")}
        </Button>
      }
    >
      {t("reservas.hoursMissing.body")}
    </Callout>
  );
}

function Tabs() {
  const { t, url, mode, data, href } = useReservas();
  const waiting = data.waitlist?.enabled ? data.waitlist.items.filter((w) => isListed(w)).length : null;
  const items = [
    { key: "agenda" as const, label: t(mode === "services" ? "reservas.tab.agenda.services" : "reservas.tab.agenda.capacity") },
    {
      key: "waitlist" as const,
      label: waiting !== null && waiting > 0 ? t("reservas.tab.waitlist.count", { count: waiting }) : t("reservas.tab.waitlist"),
    },
    { key: "settings" as const, label: t("reservas.tab.settings") },
  ];
  return (
    <nav aria-label={t("reservas.tabs.label")} className="min-w-0 overflow-x-auto border-b border-border">
      <ul className="flex min-w-max gap-1">
        {items.map((i) => {
          const current = url.tab === i.key;
          return (
            <li key={i.key}>
              <Link
                href={href({ tab: i.key })}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "-mb-px inline-flex h-10 items-center border-b-2 px-3 text-sm whitespace-nowrap",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  current ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {i.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Overlays({ overlay, close }: { overlay: Overlay | null; close: () => void }) {
  const { mode } = useReservas();
  if (!overlay) return null;
  switch (overlay.kind) {
    case "detail":
      return <BookingDetailSheet key={overlay.id} id={overlay.id} initial={overlay.booking} onClose={close} />;
    case "new":
      return mode === "services" ? (
        <ServicesBookingDialog booking={null} prefill={overlay.prefill} onClose={close} />
      ) : (
        <CapacityBookingDialog booking={null} prefill={overlay.prefill} onClose={close} />
      );
    case "move":
      return mode === "services" ? (
        <ServicesBookingDialog booking={overlay.booking} prefill={{}} onClose={close} />
      ) : (
        <CapacityBookingDialog booking={overlay.booking} prefill={{}} onClose={close} />
      );
    case "cancel":
      return <CancelDialog booking={overlay.booking} onClose={close} />;
    case "walkin":
      return <WalkinDialog onClose={close} />;
    case "block":
      return <BlockDialog prefill={overlay.prefill} onClose={close} />;
    case "hour":
      return <HourPanel key={`${overlay.date}-${overlay.time}`} date={overlay.date} time={overlay.time} onClose={close} />;
  }
}
