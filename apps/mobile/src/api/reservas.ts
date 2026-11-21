import { getLocales } from "expo-localization";

import { API_URL, RESERVAS_DEMO, RESERVAS_DEMO_STATE } from "@/config";
import { localeOf, t } from "@/i18n/t";
import { addDays, openSpan, parseHHMM, wallClock, type BizNow, type LocalDate, type Minutes } from "@/lib/reservas-model";

import { authedFetch } from "./client";
import { ApiError, errorOf } from "./errors";

/**
 * Reservas, as the app reads it (spec 044, research D1). One adapter between
 * the API's frozen contract — `specs/043-reservas/contracts/lite-api.md` §1–§7
 * and `specs/045-…/contracts/lite-api.md` §4–§5, both of 2026-10-22, which the
 * app's proposal (`specs/044-…/contracts/app-needs.md`) was reconciled to — and
 * the model the screens use (`data-model.md`). If a route or a field changes,
 * it changes here and nowhere else.
 *
 * The routes go through `authedFetch` (same credential, same one renewal,
 * same refusals as the typed client) and read the wire by hand. They are in
 * `openapi.json` since `99f12805`; spec 069 adds the ones the web already
 * used — move, ask to confirm, cancel with its options and preview, the
 * offers — with the shapes of `schema.gen.ts` (`MoveIn`, `CancelIn`,
 * `CancelPreviewOut`, `OfferOut`, `CalendarStatus`).
 *
 * In a development build, `EXPO_PUBLIC_RESERVAS_DEMO` swaps the HTTP source
 * for the example one (research D2). Nothing of it is ever loaded outside
 * `__DEV__`.
 */

// ── the model (data-model.md) ─────────────────────────────────────────

export type Mode = "services" | "capacity";
export type ResState = "pending" | "confirmed" | "arrived" | "done" | "noshow" | "cancelled";
export type ResAction = "confirm" | "arrived" | "noshow" | "undo" | "cancel";
export type Origin = "agent" | "person" | "walkin" | "waitlist";
export type Channel = "whatsapp" | "phone" | "in_person";
export type Weekday = 1 | 2 | 3 | 4 | 5 | 6 | 7;

/** A professional's Google calendar as the API keeps it (`CalendarStatus.status`, spec 069 R13.7). */
export type CalendarState = "none" | "pending" | "connected" | "needs_calendar" | "needs_reauth" | "error";
/**
 * `calendar` is what spec 044 read («google» only when connected) and stays for
 * what compares it; `calendarState` is every state the API says, and
 * `calendarBusy` the business's own Google still blocking their hours.
 */
export type Pro = { id: string; name: string; calendar: "google" | "none"; calendarState?: CalendarState; calendarBusy?: boolean };
export type Service = { id: string; name: string; durationMin: number; price: number | null; proIds: string[] | null };
export type Shift = { name: string; from: Minutes; to: Minutes; everyMin: number };
/** A block covers the arrival times from `from` to `until`, both included (043 §6). */
export type Block = { id: string; date: LocalDate; from: Minutes; until: Minutes; reason: string; shift: string | null };

export type CapacityConfig = {
  /** The word for people, from the kind of business (043 §1: the screen puts the words). */
  unit: string;
  kind?: string | null;
  capacity: number;
  stayMin: number;
  maxParty: number;
  walkinReserved: number;
  shifts: Shift[];
  /** Shifts closed on a weekday: worked out from the business hours. */
  closed: { weekday: number; shift: string | null }[];
  blocks: Block[];
  editable: boolean;
};

export type ResConfig = {
  mode: Mode;
  timezone: string;
  currency: string;
  hours: { weekday: Weekday; open: Minutes; close: Minutes }[];
  hoursLabel: string | null;
  hoursMissing: boolean;
  waitlist: { enabled: boolean; leadHours: number; editable: boolean };
  confirmation: { enabled: boolean; when: "24h" | "same_day_12" | "3h"; editable: boolean };
  services: { stepMin: number; team: Pro[]; catalog: Service[] } | null;
  capacity: CapacityConfig | null;
  /** For `If-Match` on `PATCH /settings` (043 §2). */
  version: number;
  /** Spec 064 R1, 069 R17.1: how soon the agent may give a time (minutes; 0 is none). Read as 60 when absent, the API's default. */
  agent?: { minNoticeMin: number };
  /** Spec 069 R17.1: the WhatsApp reminder 24 hours before (`reminder_enabled`). */
  reminders?: boolean;
};

/** Spec 064 R1.2: the only notices the API takes for the agent. */
export const NOTICE_MINUTES = [0, 15, 30, 60, 120, 240, 1440] as const;

/** One line of a reservation's history (043 §4 `events`): the words are the screen's. */
export type ResEvent = { kind: string; at: string; actor: string | null; data: Record<string, unknown> };

export type Reservation = {
  id: string;
  /** For `If-Match` on every action (043 §4). */
  version: number;
  date: LocalDate;
  start: Minutes;
  end: Minutes;
  state: ResState;
  /** `name` is empty for a walk-in without one: the screen says «Sin reserva». */
  customer: { name: string; phone: string | null; conversationId?: string | null };
  origin: Origin;
  channel: Channel;
  by: string | null;
  createdAt: string;
  arrivedAt: string | null;
  /** When it arrived, in the business's wall time («HH:MM»). */
  arrivedLocal: string | null;
  service: { id: string; name: string; durationMin: number; price: number | null } | null;
  pro: { id: string; name: string } | null;
  partySize: number | null;
  conflict: { source: "google"; label: string } | null;
  /** Aforo: minutes late, from the API (043 §4 `late_minutes`). */
  lateMinutes: number | null;
  /** Only the detail read carries them; lists come with `[]`. */
  events: ResEvent[];
  actions: ResAction[];
  /**
   * Spec 069 (R14.1): what the API allows besides `actions` and the phone now
   * offers too — moving it and asking the customer to confirm. Kept apart so
   * `ResAction` stays what every screen and the example API already name.
   */
  moreActions?: MoreAction[];
};

export type MoreAction = "move" | "request_confirmation";

/** Spec 069 (R14.2): what a cancellation does besides cancelling (`CancelIn`). */
export type CancelOptions = { notify: boolean; offerSlot: boolean };

/** Whether the slot of a cancellation can go to the waitlist (`CancelPreviewOut`). */
export type CancelPreview = { canOffer: boolean; candidates: number; whyNot: "waitlist_off" | "too_soon" | "nobody_fits" | "not_services" | null };

/** Spec 069 (R14.3): where a reservation goes (`MoveIn`); what does not change is left out. */
export type MoveRequest = { date: LocalDate; time: Minutes; proId?: string | null; partySize?: number; notify: boolean };

/** A freed slot the agent is offering to the waitlist, one person at a time (`OfferOut`, spec 069 R16.2). */
export type Offer = {
  id: string;
  status: "running" | "filled" | "empty" | "stopped";
  createdAt: string;
  windowMin: number;
  slot: { date: LocalDate; start: Minutes; end: Minutes; service: string | null; pro: string | null; seats: number | null };
  candidates: { name: string | null; position: number; status: string; deadlineAt: string | null }[];
  cancelledBy: string | null;
};

export type Slot = { date: LocalDate; time: Minutes; inside: number; capacity: number; blocked: string | null; closed: boolean };
export type DayOccupancy = { date: LocalDate; pct: number | null; closed: boolean };
export type FreeSlot = { time: Minutes; pro: { id: string; name: string } | null; left: number | null; full: boolean };

export type WaitEntry = {
  id: string;
  name: string;
  phone: string | null;
  wants: { date: LocalDate | null; time: Minutes | null; until?: LocalDate | null; partySize: number | null; service: string | null; pro: string | null; text: string | null };
  state: "waiting" | "offered" | "accepted";
  fits: boolean | null;
  offeredUntil: string | null;
  joinedBy: "agent" | "person";
  by: string | null;
  joinedAt: string;
};

export type Range = { items: Reservation[]; now: BizNow };
export type Occupancy = { slots: Slot[]; days: DayOccupancy[] };
export type NewReservation = {
  date: LocalDate;
  time: Minutes;
  customer: { name: string; phone: string | null };
  serviceId?: string;
  proId?: string | null;
  partySize?: number;
};
export type ConfigPatch = {
  waitlist?: Partial<{ enabled: boolean; leadHours: number }>;
  confirmation?: Partial<{ enabled: boolean; when: ResConfig["confirmation"]["when"] }>;
  capacity?: Partial<{ capacity: number; stayMin: number; maxParty: number; walkinReserved: number }>;
  /** Spec 069 R17.1. */
  agent?: { minNoticeMin: number };
  reminders?: boolean;
};

/**
 * Someone on the waitlist. At the door (`inPerson`, the walk-in) no phone is
 * asked (064 R3.7); put there by hand from the list, the phone is required
 * (spec 069 R16.1) and so is what they want.
 */
export type JoinWaitlist = {
  partySize: number;
  name: string | null;
  date: LocalDate | null;
  time: Minutes | null;
  phone?: string | null;
  inPerson?: boolean;
  serviceId?: string | null;
  proId?: string | null;
  until?: LocalDate | null;
};

export interface ReservasSource {
  config(): Promise<ResConfig>;
  range(from: LocalDate, to: LocalDate): Promise<Range>;
  /** One reservation with its history (043 §4 `GET /bookings/{id}`). */
  booking(id: string): Promise<Reservation>;
  occupancy(from: LocalDate, to: LocalDate): Promise<Occupancy>;
  /** `exclude`: a reservation being moved, so its own time counts as free (spec 069 R14.3). */
  freeSlots(q: { date: LocalDate; serviceId?: string; proId?: string | null; partySize?: number; exclude?: string }): Promise<FreeSlot[]>;
  create(body: NewReservation, idempotencyKey: string): Promise<Reservation>;
  act(r: Pick<Reservation, "id" | "version">, action: ResAction): Promise<Reservation>;
  /** Cancel, telling the customer or not and offering the slot to the waitlist or not (spec 069 R14.2). */
  cancel(r: Pick<Reservation, "id" | "version">, opts: CancelOptions): Promise<Reservation>;
  cancelPreview(id: string): Promise<CancelPreview>;
  move(r: Pick<Reservation, "id" | "version">, body: MoveRequest): Promise<Reservation>;
  requestConfirmation(r: Pick<Reservation, "id" | "version">): Promise<Reservation>;
  walkIn(body: { partySize: number; name: string | null }, idempotencyKey: string): Promise<Reservation>;
  waitlist(): Promise<WaitEntry[]>;
  joinWaitlist(body: JoinWaitlist, idempotencyKey: string): Promise<void>;
  /** The slots being offered now (spec 069 R16.2). */
  offers(): Promise<Offer[]>;
  stopOffer(id: string): Promise<Offer>;
  offer(id: string): Promise<void>;
  removeWait(id: string): Promise<void>;
  patchConfig(body: ConfigPatch, version: number): Promise<ResConfig>;
  block(body: { date: LocalDate; from: Minutes; until: Minutes; reason: string }, idempotencyKey: string): Promise<void>;
  unblock(id: string): Promise<void>;
}

// ── the wire (043 lite-api.md) ────────────────────────────────────────

type Wire = Record<string, unknown>;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strOrNull = (v: unknown): string | null => (typeof v === "string" ? v : null);
const num = (v: unknown): number => (typeof v === "number" ? v : 0);
const numOrNull = (v: unknown): number | null => (typeof v === "number" ? v : null);
const obj = (v: unknown): Wire | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Wire) : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const objs = (v: unknown): Wire[] => arr(v).map(obj).filter((x): x is Wire => x !== null);
const time = (v: unknown): Minutes | null => (typeof v === "string" && /^\d{1,2}:\d{2}$/.test(v) ? parseHHMM(v) : null);

const STATES: readonly ResState[] = ["pending", "confirmed", "arrived", "done", "noshow", "cancelled"];
/** The API's action names (043 §4 `allowed`) and the app's; `move` and `request_confirmation` go in `moreActions` (spec 069). */
const ACTION_IN: Record<string, ResAction> = { confirm: "confirm", arrive: "arrived", noshow: "noshow", undo: "undo", cancel: "cancel" };
const MORE_IN: Record<string, MoreAction> = { move: "move", request_confirmation: "request_confirmation" };
const CALENDAR_STATES: readonly CalendarState[] = ["none", "pending", "connected", "needs_calendar", "needs_reauth", "error"];

/**
 * `calendar` says connected or not, as spec 044 read it; `calendarState` is
 * added only when it says more (pending, a calendar to choose, to connect
 * again, failing), and `calendarBusy` only when it is so.
 */
function calendarOf(w: Wire | null): Pick<Pro, "calendar" | "calendarState" | "calendarBusy"> {
  const status = CALENDAR_STATES.find((s) => s === w?.status) ?? "none";
  return {
    calendar: status === "connected" ? "google" : "none",
    ...(status !== "connected" && status !== "none" ? { calendarState: status } : {}),
    ...(w?.business_busy === true ? { calendarBusy: true } : {}),
  };
}
const ACTION_OUT: Record<ResAction, string> = { confirm: "confirm", arrived: "arrive", noshow: "noshow", undo: "undo", cancel: "cancel" };
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;

/** The word for people per kind of business (043 §1), in the phone's language. */
function unitFor(kind: string | null): string {
  const locale = localeOf(getLocales()[0]?.languageCode);
  const key = (["restaurant", "bar", "classes", "tours", "rooms", "spa"] as const).find((k) => k === kind) ?? "other";
  return t(locale, `reservas.unit.${key}`);
}

/** «HH:MM» of an instant in the business's zone. */
function localTime(iso: string | null, tz: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : hhmmOut(wallClock(tz, d).minutes);
}

export function toConfig(s: Wire, staff: Wire[] | null, services: Wire[] | null, blocks: Wire[] | null): ResConfig {
  const mode: Mode = s.mode === "capacity" ? "capacity" : "services";
  const bh = obj(s.business_hours) ?? {};
  const hours = DAYS.flatMap((day, i) =>
    objs(bh[day]).map((span) => ({ weekday: (i + 1) as Weekday, open: time(span.from) ?? 0, close: time(span.to) ?? 0 })),
  );
  const waitlist = obj(s.waitlist) ?? {};
  const confirmation = obj(s.confirmation) ?? {};
  const cap = obj(s.capacity);
  const schedule = obj(cap?.schedule) ?? {};
  const step = num(schedule.step_minutes) || 30;
  const shifts: Shift[] =
    schedule.model === "slots"
      ? [{ name: "", from: time(schedule.from) ?? 0, to: time(schedule.to) ?? 0, everyMin: step }]
      : objs(schedule.shifts).map((x) => ({ name: str(x.name), from: time(x.from) ?? 0, to: time(x.to) ?? 0, everyMin: step }));
  // A shift is closed on a weekday when no span of the business hours covers its arrivals.
  const closed = ([1, 2, 3, 4, 5, 6, 7] as const).flatMap((wd) =>
    shifts
      .filter((sh) => !hours.some((h) => h.weekday === wd && h.open <= sh.from && h.close >= sh.to))
      .map((sh) => ({ weekday: wd, shift: sh.name })),
  );
  const kind = strOrNull(s.capacity_kind);
  const toBlock = (b: Wire): Block => {
    const from = time(b.from) ?? 0;
    return { id: str(b.id), date: str(b.date), from, until: time(b.until) ?? from, reason: str(b.label), shift: shifts.find((sh) => sh.from === from)?.name ?? null };
  };
  return {
    mode,
    timezone: str(s.timezone) || "America/Santiago",
    currency: str(s.currency) || "CLP",
    hours,
    hoursLabel: strOrNull(s.business_hours_label),
    hoursMissing: s.hours_missing === true,
    waitlist: { enabled: waitlist.enabled === true, leadHours: Math.round(num(waitlist.lead_minutes) / 60) || 2, editable: true },
    confirmation: {
      enabled: confirmation.enabled === true,
      when: confirmation.when === "same_day_12" || confirmation.when === "3h" ? confirmation.when : "24h",
      editable: true,
    },
    services:
      mode === "services"
        ? {
            stepMin: num(s.slot_step_minutes) || 30,
            team: (staff ?? []).map((p) => ({ id: str(p.id), name: str(p.name), ...calendarOf(obj(p.calendar)) })),
            catalog: (services ?? []).map((x) => ({
              id: str(x.id),
              name: str(x.name),
              durationMin: num(x.duration_minutes),
              price: numOrNull(obj(x.price)?.amount_minor),
              proIds: x.staff === "some" ? arr(x.staff_ids).map(String) : null,
            })),
          }
        : null,
    capacity: cap
      ? {
          unit: unitFor(kind),
          kind,
          capacity: num(cap.seats),
          stayMin: num(cap.stay_minutes),
          maxParty: num(cap.max_party),
          walkinReserved: num(cap.walkin_hold),
          shifts,
          closed,
          blocks: (blocks ?? []).map(toBlock),
          editable: true,
        }
      : null,
    version: num(s.version),
    agent: { minNoticeMin: typeof obj(s.agent)?.min_notice_minutes === "number" ? num(obj(s.agent)?.min_notice_minutes) : 60 },
    reminders: s.reminder_enabled !== false,
  };
}

export function toReservation(w: Wire, tz: string): Reservation {
  const local = obj(w.local) ?? {};
  const contact = obj(w.contact) ?? {};
  const service = obj(w.service);
  const staff = obj(w.staff);
  const clash = obj(w.clash);
  const price = obj(w.price);
  const createdBy = obj(w.created_by);
  const state = STATES.includes(w.status as ResState) ? (w.status as ResState) : "pending";
  const channel = w.channel === "phone" || w.channel === "in_person" ? w.channel : "whatsapp";
  const origin = w.origin === "person" || w.origin === "walkin" || w.origin === "waitlist" ? w.origin : "agent";
  const arrivedAt = strOrNull(w.arrived_at);
  return {
    id: str(w.id),
    version: num(w.version),
    date: str(local.date),
    start: time(local.start) ?? 0,
    end: time(local.end) ?? 0,
    state,
    customer: { name: str(contact.name), phone: strOrNull(contact.phone), conversationId: strOrNull(contact.conversation_id) },
    origin,
    channel,
    by: createdBy?.kind === "person" ? strOrNull(createdBy.name) : null,
    createdAt: str(w.created_at),
    arrivedAt,
    arrivedLocal: localTime(arrivedAt, tz),
    service: service ? { id: str(service.id), name: str(service.name), durationMin: num(service.duration_minutes), price: numOrNull(price?.amount_minor) } : null,
    pro: staff ? { id: str(staff.id), name: str(staff.name) } : null,
    partySize: w.mode === "services" ? null : numOrNull(w.party_size),
    conflict: clash ? { source: "google", label: "Ocupado" } : null,
    lateMinutes: numOrNull(w.late_minutes),
    events: objs(w.events).map((e) => ({ kind: str(e.kind), at: str(e.at), actor: strOrNull(obj(e.actor)?.name), data: obj(e.data) ?? {} })),
    actions: arr(w.allowed)
      .map((a) => ACTION_IN[String(a)])
      .filter((a): a is ResAction => a !== undefined),
    moreActions: arr(w.allowed)
      .map((a) => MORE_IN[String(a)])
      .filter((a): a is MoreAction => a !== undefined),
  };
}

export function toCancelPreview(w: Wire): CancelPreview {
  const why = w.why_not;
  return {
    canOffer: w.can_offer === true,
    candidates: num(w.candidates),
    whyNot: why === "waitlist_off" || why === "too_soon" || why === "nobody_fits" || why === "not_services" ? why : null,
  };
}

export function toOffer(w: Wire): Offer {
  const slot = obj(w.slot) ?? {};
  const local = obj(slot.local) ?? {};
  const status = w.status === "filled" || w.status === "empty" || w.status === "stopped" ? w.status : "running";
  return {
    id: str(w.id),
    status,
    createdAt: str(w.created_at),
    windowMin: num(w.window_minutes),
    slot: {
      date: str(local.date),
      start: time(local.start) ?? 0,
      end: time(local.end) ?? 0,
      service: strOrNull(obj(slot.service)?.name),
      pro: strOrNull(obj(slot.staff)?.name),
      seats: numOrNull(slot.seats),
    },
    candidates: objs(w.candidates)
      .map((c) => ({ name: strOrNull(c.name), position: num(c.position), status: str(c.status), deadlineAt: strOrNull(c.deadline_at) }))
      .sort((a, b) => a.position - b.position),
    cancelledBy: strOrNull(w.cancelled_by_name),
  };
}

export function toWaitEntry(w: Wire): WaitEntry {
  const contact = obj(w.contact) ?? {};
  const desired = obj(w.desired) ?? {};
  const offer = obj(w.offer);
  const joined = obj(w.joined) ?? {};
  return {
    id: str(w.id),
    name: str(contact.name),
    phone: strOrNull(contact.phone),
    wants: {
      date: strOrNull(desired.date),
      time: time(desired.time),
      until: strOrNull(desired.until),
      partySize: numOrNull(w.party_size),
      service: strOrNull(obj(w.service)?.name),
      pro: strOrNull(obj(w.staff)?.name),
      text: null,
    },
    state: offer ? "offered" : w.status === "accepted" ? "accepted" : "waiting",
    fits: typeof w.fits_now === "boolean" ? w.fits_now : null,
    offeredUntil: strOrNull(offer?.deadline_at),
    joinedBy: joined.kind === "person" ? "person" : "agent",
    by: strOrNull(joined.name),
    joinedAt: str(joined.at),
  };
}

const hhmmOut = (m: Minutes) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

// ── the HTTP source ───────────────────────────────────────────────────

const BASE = "/console/lite/reservas";

async function request(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<unknown> {
  let res: Response;
  try {
    res = await authedFetch(`${API_URL}${path}`, {
      method,
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, "offline");
  }
  const text = await res.text().catch(() => "");
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }
  if (!res.ok) throw errorOf(res.status, parsed);
  return parsed;
}

const q = (params: Record<string, string | number | null | undefined>) => {
  const s = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");
  return s ? `?${s}` : "";
};

/** The API's refusal, under the app's words: a walk-in that does not fit is «no_room»; outside service, «closed» (043 §4). */
function asWalkInError(e: unknown): unknown {
  if (e instanceof ApiError && e.code === "slot_taken") return new ApiError(e.status, "no_room", e.info);
  if (e instanceof ApiError && e.code === "invalid_transition") return new ApiError(e.status, "closed", e.info);
  return e;
}

export function httpSource(): ReservasSource {
  // The last configuration read: the business's zone and team, for what the API leaves to the screen.
  let last: ResConfig | null = null;
  const tz = () => last?.timezone ?? "America/Santiago";
  const config = async (): Promise<ResConfig> => {
    const s = (await request("GET", `${BASE}/settings`)) as Wire;
    const services = s.mode !== "capacity";
    const today = wallClock(str(s.timezone) || "America/Santiago").date;
    const [staff, catalog, blocks] = await Promise.all([
      services ? request("GET", `${BASE}/staff?archived=false`) : null,
      services ? request("GET", `${BASE}/services?archived=false`) : null,
      services ? null : request("GET", `${BASE}/blocks${q({ from: today, to: addDays(today, 60) })}`),
    ]);
    last = toConfig(s, staff ? objs(obj(staff)?.items) : null, catalog ? objs(obj(catalog)?.items) : null, blocks ? objs(obj(blocks)?.items) : null);
    return last;
  };
  const bookings = async (from: LocalDate, to: LocalDate) =>
    objs(obj(await request("GET", `${BASE}/bookings${q({ from, to })}`))?.items).map((b) => toReservation(b, tz()));

  return {
    config,
    range: async (from, to) => {
      const items = await bookings(from, to);
      // The list carries no «now»: the business's wall clock, read now (research D3).
      return { items, now: { ...wallClock(tz()), readAt: Date.now() } };
    },
    booking: async (id) => toReservation((await request("GET", `${BASE}/bookings/${encodeURIComponent(id)}`)) as Wire, tz()),
    occupancy: async (from, to) => {
      const c = last ?? (await config());
      if (c.mode === "services") {
        // No occupancy route in Servicios (043 §5): booked hours over open hours of the team, per day.
        const items = await bookings(from, to);
        const team = Math.max(1, c.services?.team.length ?? 1);
        const days: DayOccupancy[] = [];
        for (let d = from; d <= to; d = addDays(d, 1)) {
          const span = openSpan(c, d);
          if (!span) {
            days.push({ date: d, pct: null, closed: true });
            continue;
          }
          const booked = items.filter((r) => r.date === d && r.state !== "cancelled").reduce((a, r) => a + (r.end - r.start), 0);
          days.push({ date: d, pct: Math.min(100, Math.round((booked / ((span.close - span.open) * team)) * 100)), closed: false });
        }
        return { slots: [], days };
      }
      const w = (await request("GET", `${BASE}/occupancy${q({ from, to })}`)) as Wire;
      const seats = num(w.seats);
      const slots: Slot[] = objs(w.days).flatMap((d) =>
        objs(d.slots).map((x) => ({
          date: str(d.date),
          time: time(x.time) ?? 0,
          inside: num(x.present),
          capacity: seats,
          blocked: strOrNull(obj(x.blocked)?.label),
          closed: d.closed === true,
        })),
      );
      const days: DayOccupancy[] = objs(w.days).map((d) => {
        const open = slots.filter((x) => x.date === str(d.date) && !x.blocked);
        return {
          date: str(d.date),
          closed: d.closed === true,
          pct: d.closed === true || open.length === 0 || seats === 0 ? null : Math.round((open.reduce((a, x) => a + x.inside / seats, 0) / open.length) * 100),
        };
      });
      return { slots, days };
    },
    freeSlots: async ({ date, serviceId, proId, partySize, exclude }) => {
      const c = last ?? (await config());
      const w = (await request("GET", `${BASE}/slots${q({ date, service_id: serviceId, staff_id: proId, party_size: partySize, exclude })}`)) as Wire;
      if (w.closed === true) return [];
      return objs(w.slots).map((x) => {
        if (c.mode === "services") {
          const id = proId ?? str(arr(x.staff_ids)[0]);
          const pro = c.services?.team.find((p) => p.id === id);
          return { time: time(x.time) ?? 0, pro: pro ? { id: pro.id, name: pro.name } : id ? { id, name: "" } : null, left: null, full: false };
        }
        return { time: time(x.time) ?? 0, pro: null, left: numOrNull(x.left), full: x.fits !== true };
      });
    },
    create: async (b, key) =>
      toReservation(
        (await request(
          "POST",
          `${BASE}/bookings`,
          {
            date: b.date,
            time: hhmmOut(b.time),
            ...(b.serviceId ? { service_id: b.serviceId, staff_id: b.proId ?? null } : {}),
            ...(b.partySize ? { party_size: b.partySize } : {}),
            contact: { name: b.customer.name, phone: b.customer.phone },
            note: null,
            join_waitlist: false,
            notify: true,
          },
          { "Idempotency-Key": key },
        )) as Wire,
        tz(),
      ),
    act: async (r, action) =>
      toReservation(
        (await request(
          "POST",
          `${BASE}/bookings/${encodeURIComponent(r.id)}/${ACTION_OUT[action]}`,
          action === "cancel" ? { notify: true } : undefined,
          { "If-Match": String(r.version) },
        )) as Wire,
        tz(),
      ),
    cancel: async (r, opts) =>
      toReservation(
        (await request(
          "POST",
          `${BASE}/bookings/${encodeURIComponent(r.id)}/cancel`,
          { notify: opts.notify, offer_slot: opts.offerSlot },
          { "If-Match": String(r.version) },
        )) as Wire,
        tz(),
      ),
    cancelPreview: async (id) => toCancelPreview((await request("GET", `${BASE}/bookings/${encodeURIComponent(id)}/cancel-preview`)) as Wire),
    move: async (r, b) =>
      toReservation(
        (await request(
          "POST",
          `${BASE}/bookings/${encodeURIComponent(r.id)}/move`,
          {
            date: b.date,
            time: hhmmOut(b.time),
            ...(b.proId !== undefined ? { staff_id: b.proId } : {}),
            ...(b.partySize !== undefined ? { party_size: b.partySize } : {}),
            notify: b.notify,
          },
          { "If-Match": String(r.version) },
        )) as Wire,
        tz(),
      ),
    requestConfirmation: async (r) =>
      toReservation(
        (await request("POST", `${BASE}/bookings/${encodeURIComponent(r.id)}/request-confirmation`, undefined, { "If-Match": String(r.version) })) as Wire,
        tz(),
      ),
    offers: async () => objs(obj(await request("GET", `${BASE}/offers${q({ status: "running" })}`))?.items).map(toOffer),
    stopOffer: async (id) => toOffer((await request("POST", `${BASE}/offers/${encodeURIComponent(id)}/stop`)) as Wire),
    walkIn: async (b, key) => {
      try {
        return toReservation((await request("POST", `${BASE}/walkins`, { party_size: b.partySize, name: b.name }, { "Idempotency-Key": key })) as Wire, tz());
      } catch (e) {
        throw asWalkInError(e);
      }
    },
    waitlist: async () => {
      const today = wallClock(tz()).date;
      const w = (await request("GET", `${BASE}/waitlist${q({ from: today, to: addDays(today, 30) })}`)) as Wire;
      return objs(w.items).map(toWaitEntry);
    },
    joinWaitlist: async (b, key) => {
      await request(
        "POST",
        `${BASE}/waitlist`,
        {
          name: b.name ?? "",
          phone: b.phone ?? null,
          party_size: b.partySize,
          date: b.date,
          time: b.time != null ? hhmmOut(b.time) : null,
          // At the door unless the person typed a phone for it (064 R3.7: only in person goes without).
          in_person: b.inPerson ?? !b.phone,
          ...(b.serviceId ? { service_id: b.serviceId } : {}),
          ...(b.proId ? { staff_id: b.proId } : {}),
          ...(b.until ? { until: b.until } : {}),
        },
        { "Idempotency-Key": key },
      );
    },
    offer: async (id) => {
      await request("POST", `${BASE}/waitlist/${encodeURIComponent(id)}/offer`);
    },
    removeWait: async (id) => {
      await request("POST", `${BASE}/waitlist/${encodeURIComponent(id)}/remove`);
    },
    patchConfig: async (b, version) => {
      await request(
        "PATCH",
        `${BASE}/settings`,
        {
          ...(b.waitlist
            ? { waitlist: { ...(b.waitlist.enabled !== undefined ? { enabled: b.waitlist.enabled } : {}), ...(b.waitlist.leadHours !== undefined ? { lead_minutes: b.waitlist.leadHours * 60 } : {}) } }
            : {}),
          ...(b.confirmation ? { confirmation: b.confirmation } : {}),
          ...(b.capacity
            ? {
                capacity: {
                  ...(b.capacity.capacity !== undefined ? { seats: b.capacity.capacity } : {}),
                  ...(b.capacity.stayMin !== undefined ? { stay_minutes: b.capacity.stayMin } : {}),
                  ...(b.capacity.maxParty !== undefined ? { max_party: b.capacity.maxParty } : {}),
                  ...(b.capacity.walkinReserved !== undefined ? { walkin_hold: b.capacity.walkinReserved } : {}),
                },
              }
            : {}),
          ...(b.agent ? { agent: { min_notice_minutes: b.agent.minNoticeMin } } : {}),
          ...(b.reminders !== undefined ? { reminder_enabled: b.reminders } : {}),
        },
        { "If-Match": String(version) },
      );
      // The answer is the whole settings; staff, services and blocks did not change, but re-read them with it.
      return config();
    },
    block: async (b, key) => {
      await request("POST", `${BASE}/blocks`, { date: b.date, from: hhmmOut(b.from), until: hhmmOut(b.until), label: b.reason }, { "Idempotency-Key": key });
    },
    unblock: async (id) => {
      await request("POST", `${BASE}/blocks/${encodeURIComponent(id)}/remove`);
    },
  };
}

// ── which source ──────────────────────────────────────────────────────

/** The example source, only in a development build that asked for it (research D2). */
export type Demo = ReservasSource & {
  mode: Mode;
  me<T extends { nav: string[]; client: { modules: string[] } }>(me: T): T;
  notices(): Promise<{ kinds: string[]; quiet_outside_hours: boolean }>;
  setNotices(body: { kinds?: string[]; quiet_outside_hours?: boolean }): Promise<{ kinds: string[]; quiet_outside_hours: boolean }>;
  nextFor(contactName: string): { id: string; date: LocalDate; start: string; label: string } | null;
};

export const demo: Demo | null =
  __DEV__ && RESERVAS_DEMO
    ? // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require("./reservas-demo") as typeof import("./reservas-demo")).createDemo(RESERVAS_DEMO, RESERVAS_DEMO_STATE)
    : null;

let http: ReservasSource | null = null;

export function reservasSource(): ReservasSource {
  if (demo) return demo;
  http ??= httpSource();
  return http;
}
