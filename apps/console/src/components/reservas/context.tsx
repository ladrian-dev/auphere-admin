"use client";

import * as React from "react";

import type { Locale, MessageKey } from "@/i18n/messages";
import type {
  Booking,
  BookingsPage,
  CapacityKind,
  Occupancy,
  ReservasBlock,
  ReservasService,
  ReservasSettings,
  SlotOffer,
  StaffMember,
  WaitlistPage,
} from "@/lib/backend/reservas";

import { capitalize, instantLocal, relativeDay } from "./model/dates";
import type { ReservasUrl } from "./model/url-state";
import { kindOf } from "./model/vocab";

/**
 * What the page read on the server for this URL (spec 043, T022). Each part is
 * `null` when its read failed — the screen says so for that part and paints
 * the rest (the partial state), never an invented empty.
 */
export type ReservasData = {
  settings: ReservasSettings;
  staff: StaffMember[] | null;
  services: ReservasService[] | null;
  bookings: BookingsPage | null;
  occupancy: Occupancy | null;
  blocks: ReservasBlock[] | null;
  waitlist: WaitlistPage | null;
  offers: { running: SlotOffer[]; recent: SlotOffer[] } | null;
};

export type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** A new booking, prefilled from a free cell, an hour of the map, or nothing. */
export type NewPrefill = { date?: string; time?: string; staffId?: string };

export type Overlay =
  | { kind: "detail"; id: string; booking: Booking | null }
  | { kind: "new"; prefill: NewPrefill }
  | { kind: "move"; booking: Booking }
  | { kind: "cancel"; booking: Booking }
  | { kind: "walkin" }
  | { kind: "block"; prefill: { date?: string; from?: string; until?: string } }
  | { kind: "hour"; date: string; time: string };

export type ReservasCtx = {
  data: ReservasData;
  settings: ReservasSettings;
  mode: ReservasSettings["mode"];
  kind: CapacityKind;
  url: ReservasUrl;
  today: string;
  nowMinutes: number;
  now: Date;
  locale: Locale;
  t: T;
  /** The person can open the Inbox: `conversation_id` becomes a link. */
  hasInbox: boolean;
  /** Bookings with the optimistic touch of a status change in flight. */
  bookings: Booking[];
  href: (patch: Partial<ReservasUrl>) => string;
  go: (patch: Partial<ReservasUrl>) => void;
  pending: boolean;
  refresh: () => void;
  open: (overlay: Overlay | null) => void;
  /** Mark a booking optimistically while its action travels; `null` takes the mark away. */
  touch: (id: string, patch: Partial<Booking> | null) => void;
};

const Ctx = React.createContext<ReservasCtx | null>(null);

export function ReservasProvider({ value, children }: { value: ReservasCtx; children: React.ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReservas(): ReservasCtx {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useReservas outside ReservasProvider");
  return ctx;
}

/** The words of time and of people the screens share, bound to the locale and «today». */
export function useWords() {
  const { t, locale, today, settings } = useReservas();
  const kind = kindOf(settings);
  return React.useMemo(() => {
    const rel = { today: t("reservas.day.today"), tomorrow: t("reservas.day.tomorrow"), yesterday: t("reservas.day.yesterday") };
    /** «hoy», «mañana», «jue 8» — inside a sentence. */
    const day = (date: string) => {
      const out = relativeDay(date, today, locale, rel);
      return locale === "es" ? out.toLocaleLowerCase() : out;
    };
    /** «Hoy», «Mañana», «Jue 8» — a chip or a heading. */
    const dayTitle = (date: string) => capitalize(relativeDay(date, today, locale, rel));
    const at = (date: string, time: string) => t("reservas.when.at", { day: day(date), time });
    const instant = (iso: string) => {
      const local = instantLocal(iso, settings.timezone);
      return t("reservas.when.instant", { day: day(local.date), time: local.time });
    };
    const unitKeyFor = (n: number) => (n === 1 ? `reservas.kind.${kind}.one` : `reservas.kind.${kind}.unit`) as MessageKey;
    /** «4 comensales», «1 plaza». */
    const people = (n: number) => t("reservas.people", { count: n, unit: t(unitKeyFor(n)) });
    const bookings = (n: number) => (n === 1 ? t("reservas.count.bookings.one") : t("reservas.count.bookings.other", { count: n }));
    return { day, dayTitle, at, instant, people, bookings, unit: t(unitKeyFor(2)), unitFor: (n: number) => t(unitKeyFor(n)) };
  }, [t, locale, today, settings.timezone, kind]);
}
