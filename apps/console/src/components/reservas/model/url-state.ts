import type { ReservasMode } from "@/lib/backend/reservas";

import { diffDays, isDay, type Period } from "./dates";

/**
 * What the URL holds on `/reservas` (spec 043, T022): the sub-tab, the view
 * and the period — two separate controls (Requisito 8.2) — the day, and the
 * professional. A link to a day is a link anyone can open again; nothing of
 * this lives only in memory.
 */
export type Tab = "agenda" | "waitlist" | "settings";
export type View = "grid" | "list";
export type ReservasUrl = { tab: Tab; view: View; period: Period; date: string; staff: string | null };

export type SearchParams = Record<string, string | string[] | undefined>;

const TABS: readonly Tab[] = ["agenda", "waitlist", "settings"];
const VIEWS: readonly View[] = ["grid", "list"];
const PERIODS: readonly Period[] = ["day", "week", "month"];
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Far enough for any agenda, near enough that a typo is not a query for the year 9999. */
const MAX_DAYS_AWAY = 5 * 366;

/** Servicios opens on today's agenda by professional; Aforo on the week's map (spec §Clarifications). */
export function defaultPeriod(mode: ReservasMode): Period {
  return mode === "capacity" ? "week" : "day";
}

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parseReservasUrl(sp: SearchParams, ctx: { today: string; mode: ReservasMode }): ReservasUrl {
  const tab = one(sp.tab);
  const view = one(sp.view);
  const period = one(sp.period);
  const date = one(sp.date);
  const staff = one(sp.staff);
  return {
    tab: TABS.includes(tab as Tab) ? (tab as Tab) : "agenda",
    view: VIEWS.includes(view as View) ? (view as View) : "grid",
    period: PERIODS.includes(period as Period) ? (period as Period) : defaultPeriod(ctx.mode),
    date: isDay(date) && Math.abs(diffDays(ctx.today, date)) <= MAX_DAYS_AWAY ? date : ctx.today,
    staff: staff && UUID_RE.test(staff) ? staff : null,
  };
}

/**
 * The booking to open on arrival (spec 043, T026): the Panel's «Próximas de
 * hoy» link to `/reservas?booking={id}`. Only a UUID — anything else opens
 * nothing. It is not part of `ReservasUrl`: the links of the screen (tabs,
 * days) must not carry it and open the panel again.
 */
export function parseBookingParam(sp: SearchParams): string | null {
  const id = one(sp.booking);
  return id && UUID_RE.test(id) ? id : null;
}

/** `/reservas` with one booking open. */
export function bookingHref(id: string): string {
  return `/reservas?booking=${encodeURIComponent(id)}`;
}

/** The `/reservas` link for `state` changed by `patch`, without the parts that are the default. */
export function reservasHref(
  state: ReservasUrl,
  patch: Partial<ReservasUrl>,
  ctx: { today: string; mode: ReservasMode },
): string {
  const next = { ...state, ...patch };
  const params = new URLSearchParams();
  // The agenda's place survives a visit to another tab: coming back lands on the same day.
  if (next.tab !== "agenda") params.set("tab", next.tab);
  if (next.view !== "grid") params.set("view", next.view);
  if (next.period !== defaultPeriod(ctx.mode)) params.set("period", next.period);
  if (next.date !== ctx.today) params.set("date", next.date);
  if (next.staff) params.set("staff", next.staff);
  const qs = params.toString();
  return qs ? `/reservas?${qs}` : "/reservas";
}
