import { TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Button, Section, Skeleton, StatusBadge, cn, formatNumber } from "@nexus/ui";

import { capitalize, dayLabel } from "@/components/reservas/model/dates";
import { bookingHref } from "@/components/reservas/model/url-state";
import { statusKey, statusTone } from "@/components/reservas/model/vocab";
import type { Locale, MessageKey } from "@/i18n/messages";
import type { LiteReservasInfo } from "@/lib/backend/lite";
import type { Booking, CapacityKind, ReservasSummary } from "@/lib/backend/reservas";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * What the Panel knows of Reservas (spec 043, T026): the mode and kind from
 * `/me` (to name the block even when the figures fail) and the summary from
 * `GET /reservas/summary`, `null` when that read failed.
 */
export type LitePanelReservas = { info: LiteReservasInfo | null; summary: ReservasSummary | null };

/** «Próximas de hoy»: the design draws up to four. */
const UPCOMING = 4;
const DASH = "—";
const UPCOMING_HEADING = "lite-reservas-upcoming-h";

type Figure = { key: string; label: string; value: string; hint?: string };

function words(t: T, locale: Locale, kind: CapacityKind) {
  const n = (v: number) => formatNumber(v, locale);
  /** «comensales», «1 plaza»: the business's words for its people. */
  const unit = (count: number) => t((count === 1 ? `reservas.kind.${kind}.one` : `reservas.kind.${kind}.unit`) as MessageKey);
  return {
    n,
    unit,
    people: (count: number) => t("reservas.people", { count: n(count), unit: unit(count) }),
    bookings: (count: number) => (count === 1 ? t("reservas.count.bookings.one") : t("reservas.count.bookings.other", { count: n(count) })),
    /** A share as the API sends it (0–100), or «—» when there is nothing to measure. */
    pct: (value: number | null | undefined, digits: number) =>
      value == null ? DASH : t("lite.reservas.pct", { pct: formatNumber(value, locale, { maximumFractionDigits: digits }) }),
    count: (value: number | null | undefined) => (value == null ? DASH : n(value)),
  };
}

/** Servicios: today, the week's occupancy and the agent's share, the month's no-shows and what the waitlist recovered. */
function servicesFigures(s: ReservasSummary, t: T, w: ReturnType<typeof words>): Figure[] {
  const today = s.today;
  return [
    {
      key: "today",
      label: t("lite.reservas.today"),
      value: w.count(today?.bookings),
      hint: today ? t("lite.reservas.today.split", { confirmed: w.n(today.confirmed), pending: w.n(today.pending) }) : undefined,
    },
    { key: "occupancy", label: t("lite.reservas.week.occupancy"), value: w.pct(s.week?.occupancy_pct, 0), hint: t("lite.reservas.week.occupancy.hint") },
    { key: "agent", label: t("lite.reservas.week.agent"), value: w.pct(s.week?.agent_share_pct, 0), hint: t("lite.reservas.week.agent.hint") },
    { key: "noshow", label: t("lite.reservas.month.noshow"), value: w.pct(s.month?.noshow_pct, 1), hint: t("lite.reservas.month.noshow.hint") },
    {
      key: "recovered",
      label: t("lite.reservas.month.recovered"),
      value: w.count(s.month?.recovered),
      // `recovered: null` with the month read is the waitlist being off (contract §5).
      hint: s.month && s.month.recovered == null ? t("lite.reservas.month.recovered.off") : t("lite.reservas.month.recovered.hint"),
    },
  ];
}

/** Aforo: people booked today, who is inside, what is unconfirmed and who waits for room. */
function capacityFigures(s: ReservasSummary, t: T, w: ReturnType<typeof words>): Figure[] {
  const today = s.today;
  const people = today?.people ?? null;
  const next = today?.arriving_next_hour ?? 0;
  return [
    {
      key: "people",
      label: t("lite.reservas.people"),
      value: w.count(people),
      hint: today && people != null ? t("lite.reservas.people.hint", { unit: w.unit(people), bookings: w.bookings(today.bookings) }) : undefined,
    },
    {
      key: "inside",
      label: t("lite.reservas.inside"),
      value: w.count(today?.inside_now),
      hint:
        [
          today?.seats != null ? t("lite.reservas.inside.of", { seats: w.n(today.seats) }) : null,
          next > 0 ? t("lite.reservas.inside.next", { people: w.people(next) }) : null,
        ]
          .filter(Boolean)
          .join(" · ") || undefined,
    },
    { key: "pending", label: t("lite.reservas.pending"), value: w.count(today?.pending), hint: t("lite.reservas.pending.hint") },
    { key: "waitlist", label: t("lite.reservas.waitlist"), value: w.count(s.waitlist?.waiting), hint: t("lite.reservas.waitlist.hint") },
  ];
}

/**
 * The Reservas block of the Panel (spec 043, T026 — Requisito 8.4; design
 * §2.1): «Agenda» in Servicios or «Ocupación» in Aforo, today's date, the
 * mode's figures and the next ones of today, each opening its booking. A
 * summary that did not load is one line inside the block — never zeros —; a
 * part that did not load is «—» with a note; nothing left today is one calm
 * line. Only for a client with the module (the caller decides).
 */
export function LiteReservasBlock({ reservas, t, locale }: { reservas: LitePanelReservas; t: T; locale: Locale }) {
  const { info, summary } = reservas;
  const mode = summary?.mode ?? info?.mode ?? null;
  const title = mode === "services" ? t("lite.reservas.title.services") : mode === "capacity" ? t("lite.reservas.title.capacity") : t("lite.reservas.title");
  const date = summary?.today?.date ? capitalize(dayLabel(summary.today.date, locale)) : undefined;

  return (
    <Section
      title={title}
      description={date}
      className="@container"
      actions={
        <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/reservas" />}>
          {t("lite.reservas.see")}
        </Button>
      }
    >
      {summary === null ? (
        <p role="status" className="flex items-center gap-2 text-sm text-pretty text-muted-foreground">
          <TriangleAlert className="size-4 shrink-0 text-status-danger" aria-hidden="true" />
          {t("lite.reservas.error")}
        </p>
      ) : (
        <SummaryBody summary={summary} kind={info?.capacity_kind ?? "restaurant"} t={t} locale={locale} />
      )}
    </Section>
  );
}

function SummaryBody({ summary, kind, t, locale }: { summary: ReservasSummary; kind: CapacityKind; t: T; locale: Locale }) {
  const w = words(t, locale, kind);
  const services = summary.mode === "services";
  const figures = services ? servicesFigures(summary, t, w) : capacityFigures(summary, t, w);
  const upcoming = summary.upcoming.slice(0, UPCOMING);
  return (
    <>
      {(summary.errors?.length ?? 0) > 0 ? (
        <p role="status" className="text-xs text-pretty text-muted-foreground">
          {t("lite.reservas.partial")}
        </p>
      ) : null}
      <dl className={cn("grid grid-cols-2 gap-3", services ? "@2xl:grid-cols-5" : "@xl:grid-cols-4")}>
        {figures.map((f) => (
          <div key={f.key} className="flex min-w-0 flex-col gap-1 rounded-md bg-muted/40 p-3">
            <dt className="text-sm text-pretty text-muted-foreground">{f.label}</dt>
            <dd className="text-2xl font-semibold tabular-nums">{f.value}</dd>
            {f.hint ? <dd className="text-xs text-pretty text-muted-foreground">{f.hint}</dd> : null}
          </div>
        ))}
      </dl>
      <div className="flex min-w-0 flex-col gap-2">
        <h3 id={UPCOMING_HEADING} className="text-sm font-medium">
          {t("lite.reservas.upcoming")}
        </h3>
        {upcoming.length === 0 ? (
          <p className="text-sm text-pretty text-muted-foreground">{t("lite.reservas.upcoming.empty")}</p>
        ) : (
          <ul aria-labelledby={UPCOMING_HEADING} className="flex min-w-0 flex-col">
            {upcoming.map((b, i) => (
              <UpcomingRow key={b.id} booking={b} first={i === 0} t={t} people={w.people} />
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

function UpcomingRow({ booking: b, first, t, people }: { booking: Booking; first: boolean; t: T; people: (n: number) => string }) {
  const name = b.contact.name ?? t("reservas.detail.walkinName");
  const sub = b.mode === "services" ? [b.service?.name, b.staff?.name].filter(Boolean).join(" · ") : people(b.party_size);
  return (
    <li className={cn(!first && "border-t border-border")}>
      <Link
        href={bookingHref(b.id)}
        className={cn(
          "flex min-h-11 min-w-0 items-center gap-3 rounded-sm px-2 py-2",
          "transition-colors duration-(--duration-hover) hover:bg-muted",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        )}
      >
        <span className="w-12 shrink-0 text-sm font-medium tabular-nums">{b.local.start}</span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-medium" title={name}>
            {name}
          </span>
          {sub ? (
            <span className="truncate text-xs text-muted-foreground" title={sub}>
              {sub}
            </span>
          ) : null}
        </span>
        <StatusBadge tone={statusTone(b.status)}>{t(statusKey(b.mode, b.status))}</StatusBadge>
      </Link>
    </li>
  );
}

/** The block while the Panel loads, at its final size: the title, the figures and three rows. */
export function LiteReservasSkeleton({ t }: { t: T }) {
  return (
    <div
      role="status"
      aria-label={t("reservas.loading")}
      aria-busy="true"
      data-slot="lite-reservas-skeleton"
      className="@container flex min-w-0 flex-col gap-(--space-stack) rounded-md bg-card p-4 ring-1 ring-foreground/10"
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-5 w-40" />
        </div>
        <Skeleton className="h-8 w-28" />
      </div>
      <div className="grid grid-cols-2 gap-3 @2xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex min-w-0 flex-col gap-1 rounded-md bg-muted/40 p-3">
            <Skeleton className="h-5 w-24 max-w-full" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-4 w-28 max-w-full" />
          </div>
        ))}
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <p className="text-sm font-medium">{t("lite.reservas.upcoming")}</p>
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </div>
    </div>
  );
}
