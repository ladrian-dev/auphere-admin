import { addDays, hhmm, openSpan, parseHHMM, type LocalDate } from "@/lib/reservas-model";

import { ApiError } from "../errors";
import type { CancelPreview, ConfigPatch, Demo, FreeSlot, Occupancy, Offer, ResAction, ResConfig, Reservation, WaitEntry } from "../reservas";
import { createDemo } from "../reservas-demo";
import type { components } from "../schema.gen";

import { CONVERSATION_IDS, LUCIA } from "./data";
import { DemoHttpError, ifMatch, refuse, route, type Route } from "./http";

type S = components["schemas"];

/**
 * Reservas in the example API: the routes `reservas.ts` (`httpSource`) calls,
 * answered by the example source of spec 044 (`reservas-demo.ts`, «Servicios»)
 * and written back in the API's wire (043 `lite-api.md`, typed from
 * `schema.gen.ts`). This is the inverse of `toConfig` / `toReservation` /
 * `toWaitEntry`: what goes out here comes back as the same model there.
 *
 * The example source waits on its own (350 ms), so these routes add no wait.
 * Its refusals (`ApiError`) go out as the API's `{"detail": {"code": …}}`.
 * What spec 069 adds to the source (move, ask to confirm, cancel with its
 * options, the offers) is used when the example has it, and answered as the
 * API would without it otherwise.
 */
let source: Demo | null = null;
let cached: ResConfig | null = null;
/** Settings the example may not keep yet (spec 069 R17.1): what was last saved, read back. */
let saved: { minNoticeMin?: number; reminders?: boolean } = {};

export function reservasDemo(): Demo {
  // The app reads the business's wall clock from the wire, so the example keeps the same one.
  source ??= createDemo("services", null, { clock: "business" });
  return source;
}

export function resetReservas(): void {
  source = null;
  cached = null;
  saved = {};
}

/** Whether the example source has a method (spec 069 adds some while this runs). */
function has<K extends keyof Demo>(demo: Demo, key: K): boolean {
  return typeof demo[key] === "function";
}

async function config(): Promise<ResConfig> {
  cached ??= await reservasDemo().config();
  return cached;
}

/** The example writes its instants with Santiago's offset (`reservas-demo.ts`, `at`); so do these. */
const OFFSET = "-03:00";
const instant = (date: LocalDate, m: number) => `${date}T${hhmm(m)}:00${OFFSET}`;

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;

type Allowed = S["BookingOut"]["allowed"][number];
const ACTION_OUT: Record<ResAction, Allowed> = { confirm: "confirm", arrived: "arrive", noshow: "noshow", undo: "undo", cancel: "cancel" };
const ACTION_IN: Record<string, ResAction> = { confirm: "confirm", arrive: "arrived", noshow: "noshow", undo: "undo", cancel: "cancel" };

/** The shape of the numbers spec 044's example makes up (`+56 9 1234 5678`). */
const DELEGATE_PHONE = /^\+56 9 \d{4} \d{2}(\d{2})$/;

/**
 * The example's numbers, as this example's (`+34 600 000 0xx`, Requisito
 * 23.3): the same last two digits. A number someone typed in comes back as
 * it was typed.
 */
function phoneOf(phone: string | null): string | null {
  const m = phone ? DELEGATE_PHONE.exec(phone) : null;
  return m ? `+34 600 000 0${m[1] ?? "00"}` : phone;
}

/**
 * The example's «Lucía Fernández» is the Bandeja's: her reservation points to
 * her conversation and carries her number, so the two screens agree.
 */
function contactOf(r: Reservation): S["BookingOut"]["contact"] {
  if (r.customer.name === LUCIA.name) return { name: LUCIA.name, phone: LUCIA.handle, conversation_id: CONVERSATION_IDS.lucia };
  return { name: r.customer.name || null, phone: phoneOf(r.customer.phone), conversation_id: r.customer.conversationId ?? null };
}

// ── the model, in the wire ────────────────────────────────────────────

function businessHours(c: ResConfig): Record<string, Record<string, string>[]> {
  const out: Record<string, Record<string, string>[]> = {};
  DAYS.forEach((day, i) => {
    const spans = c.hours.filter((h) => h.weekday === i + 1).map((h) => ({ from: hhmm(h.open), to: hhmm(h.close) }));
    if (spans.length) out[day] = spans;
  });
  return out;
}

function hoursOut(c: ResConfig): S["HoursOut"] {
  const days: Record<string, S["ShiftOut"][]> = {};
  DAYS.forEach((day, i) => {
    days[day] = c.hours.filter((h) => h.weekday === i + 1).map((h) => ({ open: hhmm(h.open), close: hhmm(h.close), overnight: false }));
  });
  return { allowed: [], days, inherits: false, label: c.hoursLabel, layout: "daily", location_id: null, revision: 1, state: "complete" };
}

export function settingsOut(c: ResConfig): S["SettingsOut"] {
  const cap = c.capacity;
  return {
    agent: { max_days_ahead: 60, min_notice_minutes: c.agent?.minNoticeMin ?? saved.minNoticeMin ?? 60 },
    business_hours: businessHours(c),
    business_hours_label: c.hoursLabel,
    capacity: cap
      ? {
          seats: cap.capacity,
          stay_minutes: cap.stayMin,
          max_party: cap.maxParty,
          walkin_hold: cap.walkinReserved,
          schedule: {
            model: "shifts",
            step_minutes: cap.shifts[0]?.everyMin ?? 30,
            shifts: cap.shifts.map((s) => ({ name: s.name, from: hhmm(s.from), to: hhmm(s.to) })),
          },
        }
      : null,
    capacity_kind: cap?.kind ?? null,
    confirmation: { enabled: c.confirmation.enabled, when: c.confirmation.when },
    currency: c.currency,
    currency_set: true,
    hours: hoursOut(c),
    hours_missing: c.hoursMissing,
    location_hours: [],
    mode: c.mode,
    release_unconfirmed: false,
    reminder_enabled: c.reminders ?? saved.reminders ?? true,
    slot_step_minutes: c.services?.stepMin ?? 30,
    timezone: c.timezone,
    version: c.version,
    waitlist: { enabled: c.waitlist.enabled, lead_minutes: c.waitlist.leadHours * 60 },
  };
}

export function staffOut(c: ResConfig): S["StaffListOut"] {
  return {
    items: (c.services?.team ?? []).map((p, i) => ({
      id: p.id,
      name: p.name,
      position: i,
      archived: false,
      email: null,
      hours: null,
      effective_hours: null,
      warnings: [],
      calendar: {
        status: p.calendarState ?? (p.calendar === "google" ? "connected" : "none"),
        business_busy: p.calendarBusy ?? false,
        account: null,
        calendar_name: null,
        last_error: null,
        last_sync_at: null,
      },
    })),
  };
}

export function servicesOut(c: ResConfig): S["ServiceListOut"] {
  return {
    items: (c.services?.catalog ?? []).map((s, i) => ({
      id: s.id,
      name: s.name,
      position: i,
      archived: false,
      category: null,
      currency: c.currency,
      duration_minutes: s.durationMin,
      // The shape of a price in the API (`schemas_business_sections.PriceOut`).
      price: s.price != null ? { kind: "amount", amount_minor: s.price } : { kind: "none" },
      staff: s.proIds ? "some" : "all",
      staff_ids: s.proIds ?? [],
      warnings: [],
    })),
  };
}

function eventOut(e: Reservation["events"][number]): S["EventOut"] {
  return { kind: e.kind, at: e.at, actor: { kind: e.actor ? "person" : "system", name: e.actor }, data: { ...e.data } };
}

export function bookingOut(r: Reservation, c: ResConfig): S["BookingOut"] {
  const cancel = [...r.events].reverse().find((e) => e.kind === "cancelled");
  const by = cancel?.data.by;
  return {
    id: r.id,
    version: r.version,
    mode: c.mode,
    status: r.state,
    starts_at: instant(r.date, r.start),
    ends_at: instant(r.date, r.end),
    local: { date: r.date, start: hhmm(r.start), end: hhmm(r.end) },
    party_size: r.partySize ?? 1,
    staff: r.pro ? { id: r.pro.id, name: r.pro.name } : null,
    any_staff: false,
    service: r.service ? { id: r.service.id, name: r.service.name, duration_minutes: r.service.durationMin } : null,
    price: r.service?.price != null ? { amount_minor: r.service.price, currency: c.currency } : null,
    contact: contactOf(r),
    origin: r.origin,
    channel: r.channel,
    created_at: r.createdAt,
    created_by: { kind: r.by ? "person" : "agent", name: r.by },
    arrived_at: r.arrivedAt,
    late_minutes: r.lateMinutes,
    clash: r.conflict ? { source: "google", local: { start: hhmm(r.start), end: hhmm(r.end) } } : null,
    cancelled:
      r.state === "cancelled"
        ? { at: cancel?.at ?? null, by: by === "customer" || by === "business" || by === "system" ? by : null, cause: null }
        : null,
    note: null,
    wants_earlier: false,
    allowed: [...r.actions.map((a) => ACTION_OUT[a]), ...(r.moreActions ?? [])],
  };
}

export function bookingDetailOut(r: Reservation, c: ResConfig): S["BookingDetailOut"] {
  return { ...bookingOut(r, c), events: r.events.map(eventOut) };
}

function slotsOut(date: LocalDate, slots: FreeSlot[], c: ResConfig): S["SlotsOut"] {
  const services = c.mode === "services";
  const first = slots.find((s) => !s.full);
  return {
    date,
    closed: openSpan(c, date) === null,
    first_fit: first ? hhmm(first.time) : null,
    slots: slots.map((s) =>
      services
        ? { time: hhmm(s.time), staff_ids: s.pro ? [s.pro.id] : [], fits: true, left: null, shift: null, why: null }
        : { time: hhmm(s.time), left: s.left, fits: !s.full, staff_ids: null, shift: null, why: null },
    ),
  };
}

function occupancyOut(o: Occupancy, c: ResConfig): S["OccupancyOut"] {
  const cap = c.capacity;
  const blockOf = (date: LocalDate, t: number) => cap?.blocks.find((b) => b.date === date && t >= b.from && t <= b.until) ?? null;
  const shiftOf = (t: number) => cap?.shifts.find((s) => t >= s.from && t <= s.to)?.name ?? null;
  return {
    seats: cap?.capacity ?? 0,
    stay_minutes: cap?.stayMin ?? 0,
    walkin_hold: cap?.walkinReserved ?? 0,
    days: o.days.map((d) => ({
      date: d.date,
      closed: d.closed,
      slots: o.slots
        .filter((s) => s.date === d.date)
        .map((s) => {
          const block = blockOf(s.date, s.time);
          return {
            time: hhmm(s.time),
            shift: shiftOf(s.time),
            present: s.inside,
            arrived: 0,
            arriving: 0,
            pending: 0,
            past: false,
            blocked: block ? { id: block.id, label: block.reason } : s.blocked ? { id: "", label: s.blocked } : null,
          };
        }),
    })),
  };
}

export function entryOut(w: WaitEntry, c: ResConfig): S["WaitlistEntryOut"] {
  const svc = c.services?.catalog.find((s) => s.name === w.wants.service);
  const pro = c.services?.team.find((p) => p.name === w.wants.pro);
  return {
    id: w.id,
    status: w.state,
    contact: { name: w.name, phone: phoneOf(w.phone), conversation_id: null },
    desired: { date: w.wants.date, time: w.wants.time != null ? hhmm(w.wants.time) : null, until: w.wants.until ?? null },
    party_size: w.wants.partySize ?? 1,
    service: w.wants.service ? { id: svc?.id ?? "", name: w.wants.service, duration_minutes: svc?.durationMin ?? 0 } : null,
    staff: w.wants.pro ? { id: pro?.id ?? "", name: w.wants.pro } : null,
    fits_now: w.fits,
    offer: w.state === "offered" ? { id: `o-${w.id}`, deadline_at: w.offeredUntil } : null,
    joined: { kind: w.joinedBy, name: w.by, at: w.joinedAt },
    booking_id: null,
    booking_local: null,
  };
}

function offerOut(w: WaitEntry, c: ResConfig): S["OfferOut"] {
  const e = entryOut(w, c);
  const start = w.wants.time ?? 0;
  return {
    id: `o-${w.id}`,
    status: "running",
    created_at: new Date().toISOString(),
    window_minutes: 15,
    cancelled_by_name: null,
    filled_booking_id: null,
    slot: {
      local: { date: w.wants.date ?? new Date().toISOString().slice(0, 10), start: hhmm(start), end: hhmm(start + (c.capacity?.stayMin ?? 30)) },
      seats: w.wants.partySize,
      service: e.service ? { id: e.service.id, name: e.service.name } : null,
      staff: e.staff,
    },
    candidates: [{ waitlist_id: w.id, name: w.name, position: 1, status: "offered", deadline_at: w.offeredUntil, answered_at: null }],
  };
}

function blockOut(b: NonNullable<ResConfig["capacity"]>["blocks"][number]): S["BlockOut"] {
  return { id: b.id, date: b.date, from: hhmm(b.from), until: hhmm(b.until), label: b.reason, created_by_name: null };
}

function offerWire(o: Offer, c: ResConfig): S["OfferOut"] {
  const svc = c.services?.catalog.find((s) => s.name === o.slot.service);
  const pro = c.services?.team.find((p) => p.name === o.slot.pro);
  return {
    id: o.id,
    status: o.status,
    created_at: o.createdAt,
    window_minutes: o.windowMin,
    cancelled_by_name: o.cancelledBy,
    filled_booking_id: null,
    slot: {
      local: { date: o.slot.date, start: hhmm(o.slot.start), end: hhmm(o.slot.end) },
      seats: o.slot.seats,
      service: o.slot.service ? { id: svc?.id ?? "", name: o.slot.service } : null,
      staff: o.slot.pro ? { id: pro?.id ?? "", name: o.slot.pro } : null,
    },
    candidates: o.candidates.map((x) => ({ waitlist_id: "", name: x.name, position: x.position, status: x.status, deadline_at: x.deadlineAt, answered_at: null })),
  };
}

function previewWire(p: CancelPreview): S["CancelPreviewOut"] {
  return { can_offer: p.canOffer, candidates: p.candidates, why_not: p.whyNot };
}

/** What the Bandeja's contact sheet shows as «Próxima reserva» (`NextBookingOut`), from the same example. */
export async function nextBookingOf(name: string): Promise<S["NextBookingOut"] | null> {
  const demo = reservasDemo();
  const next = demo.nextFor(name);
  if (!next) return null;
  const r = await demo.booking(next.id);
  return {
    id: r.id,
    starts_at: instant(r.date, r.start),
    local: { date: r.date, start: hhmm(r.start), end: hhmm(r.end) },
    status: r.state,
    service_name: r.service?.name ?? null,
    party_size: r.partySize,
  };
}

// ── the routes ────────────────────────────────────────────────────────

/** The example source's refusal, as the API words it. */
async function guarded<T>(f: () => Promise<T>): Promise<T> {
  try {
    return await f();
  } catch (e) {
    if (e instanceof ApiError) throw refuse(e.status || 500, e.code ?? "error", e.info);
    throw e;
  }
}

const own = { wait: false } as const;
const B = "/console/lite/reservas" as const;

function patchOf(body: S["SettingsPatchIn"] | null): ConfigPatch {
  const num = (v: unknown) => (typeof v === "number" ? v : undefined);
  const bool = (v: unknown) => (typeof v === "boolean" ? v : undefined);
  const patch: ConfigPatch = {};
  const w = body?.waitlist;
  if (w) {
    const lead = num(w.lead_minutes);
    patch.waitlist = { ...(bool(w.enabled) !== undefined ? { enabled: bool(w.enabled) } : {}), ...(lead !== undefined ? { leadHours: Math.round(lead / 60) } : {}) };
  }
  const cf = body?.confirmation;
  if (cf) {
    const when = cf.when === "24h" || cf.when === "same_day_12" || cf.when === "3h" ? cf.when : undefined;
    patch.confirmation = { ...(bool(cf.enabled) !== undefined ? { enabled: bool(cf.enabled) } : {}), ...(when ? { when } : {}) };
  }
  const cap = body?.capacity;
  if (cap) {
    const entries = { capacity: num(cap.seats), stayMin: num(cap.stay_minutes), maxParty: num(cap.max_party), walkinReserved: num(cap.walkin_hold) };
    patch.capacity = Object.fromEntries(Object.entries(entries).filter(([, v]) => v !== undefined));
  }
  const notice = num(body?.agent?.min_notice_minutes);
  if (notice !== undefined) patch.agent = { minNoticeMin: notice };
  const reminders = bool(body?.reminder_enabled);
  if (reminders !== undefined) patch.reminders = reminders;
  return patch;
}

/** The booking's id and the version the request says it saw (`If-Match`), or the current one. */
async function target(id: string, headers: Headers): Promise<{ id: string; version: number }> {
  return { id, version: ifMatch(headers) ?? (await reservasDemo().booking(id)).version };
}

async function act(id: string, action: Allowed, headers: Headers): Promise<Reservation> {
  const mine = ACTION_IN[action];
  if (!mine) throw refuse(409, "invalid_transition");
  return reservasDemo().act(await target(id, headers), mine);
}

export const reservasRoutes: Route[] = [
  route("get", `${B}/settings`, 200, () => guarded(async () => settingsOut(await config())), own),
  route(
    "patch",
    `${B}/settings`,
    200,
    ({ json, headers }) =>
      guarded(async () => {
        const version = ifMatch(headers) ?? (await config()).version;
        const patch = patchOf(json);
        cached = await reservasDemo().patchConfig(patch, version);
        if (patch.agent) saved.minNoticeMin = patch.agent.minNoticeMin;
        if (patch.reminders !== undefined) saved.reminders = patch.reminders;
        return settingsOut(cached);
      }),
    own,
  ),
  route("get", `${B}/staff`, 200, () => guarded(async () => staffOut(await config())), own),
  route("get", `${B}/services`, 200, () => guarded(async () => servicesOut(await config())), own),
  route(
    "get",
    `${B}/bookings`,
    200,
    ({ query }) =>
      guarded(async () => {
        const from = query.from ?? new Date().toISOString().slice(0, 10);
        const to = query.to ?? from;
        const [range, c] = await Promise.all([reservasDemo().range(from, to), config()]);
        const closed: string[] = [];
        for (let d = from; d <= to; d = addDays(d, 1)) if (openSpan(c, d) === null) closed.push(d);
        const items = query.staff_id ? range.items.filter((r) => r.pro?.id === query.staff_id) : range.items;
        return { items: items.map((r) => bookingOut(r, c)), closed_days: closed, truncated: false };
      }),
    own,
  ),
  route(
    "post",
    `${B}/bookings`,
    201,
    ({ json, headers }) =>
      guarded(async () => {
        if (!json) throw new DemoHttpError(422, { detail: [{ loc: ["body"], msg: "Field required", type: "missing" }] });
        const r = await reservasDemo().create(
          {
            date: json.date,
            time: parseHHMM(json.time),
            customer: { name: json.contact.name, phone: json.contact.phone ?? null },
            ...(json.service_id ? { serviceId: json.service_id } : {}),
            ...(json.staff_id !== undefined ? { proId: json.staff_id } : {}),
            ...(typeof json.party_size === "number" ? { partySize: json.party_size } : {}),
          },
          headers.get("Idempotency-Key") ?? `booking-${Date.now()}`,
        );
        return bookingOut(r, await config());
      }),
    own,
  ),
  route(
    "get",
    `${B}/bookings/{booking_id}`,
    200,
    ({ params }) => guarded(async () => bookingDetailOut(await reservasDemo().booking(params.booking_id), await config())),
    own,
  ),
  route("post", `${B}/bookings/{booking_id}/confirm`, 200, ({ params, headers }) => guarded(async () => bookingOut(await act(params.booking_id, "confirm", headers), await config())), own),
  route("post", `${B}/bookings/{booking_id}/arrive`, 200, ({ params, headers }) => guarded(async () => bookingOut(await act(params.booking_id, "arrive", headers), await config())), own),
  route("post", `${B}/bookings/{booking_id}/noshow`, 200, ({ params, headers }) => guarded(async () => bookingOut(await act(params.booking_id, "noshow", headers), await config())), own),
  route("post", `${B}/bookings/{booking_id}/undo`, 200, ({ params, headers }) => guarded(async () => bookingOut(await act(params.booking_id, "undo", headers), await config())), own),
  route(
    "post",
    `${B}/bookings/{booking_id}/cancel`,
    200,
    ({ params, headers, json }) =>
      guarded(async () => {
        const demo = reservasDemo();
        const offerSlot = json?.offer_slot ?? false;
        const r = has(demo, "cancel")
          ? await demo.cancel(await target(params.booking_id, headers), { notify: json?.notify ?? true, offerSlot })
          : await act(params.booking_id, "cancel", headers);
        // The offer the cancellation started, when it started one (`OfferRefOut`).
        const started = offerSlot && has(demo, "offers") ? (await demo.offers()).find((o) => o.slot.date === r.date && o.slot.start === r.start) : undefined;
        return { ...bookingOut(r, await config()), offer: started ? { id: started.id, candidates: started.candidates.length } : null };
      }),
    own,
  ),
  route(
    "get",
    `${B}/bookings/{booking_id}/cancel-preview`,
    200,
    ({ params }) =>
      guarded(async () => {
        const demo = reservasDemo();
        if (has(demo, "cancelPreview")) return previewWire(await demo.cancelPreview(params.booking_id));
        // Without it in the example: the waitlist decides, as the API's preview does.
        const [c, list] = await Promise.all([config(), demo.waitlist(), demo.booking(params.booking_id)]);
        const candidates = list.filter((w) => w.state === "waiting").length;
        const whyNot = !c.waitlist.enabled ? "waitlist_off" : candidates === 0 ? "nobody_fits" : null;
        return { can_offer: whyNot === null, candidates, why_not: whyNot };
      }),
    own,
  ),
  route(
    "post",
    `${B}/bookings/{booking_id}/move`,
    200,
    ({ params, headers, json }) =>
      guarded(async () => {
        const demo = reservasDemo();
        if (!has(demo, "move")) throw refuse(409, "invalid_transition");
        const now = await demo.booking(params.booking_id);
        const r = await demo.move(
          { id: now.id, version: ifMatch(headers) ?? now.version },
          {
            date: json?.date ?? now.date,
            time: json?.time ? parseHHMM(json.time) : now.start,
            ...(json?.staff_id !== undefined ? { proId: json.staff_id } : {}),
            ...(typeof json?.party_size === "number" ? { partySize: json.party_size } : {}),
            notify: json?.notify ?? true,
          },
        );
        return bookingOut(r, await config());
      }),
    own,
  ),
  route(
    "post",
    `${B}/bookings/{booking_id}/request-confirmation`,
    200,
    ({ params, headers }) =>
      guarded(async () => {
        const demo = reservasDemo();
        if (!has(demo, "requestConfirmation")) throw refuse(409, "invalid_transition");
        return bookingOut(await demo.requestConfirmation(await target(params.booking_id, headers)), await config());
      }),
    own,
  ),
  route(
    "get",
    `${B}/offers`,
    200,
    () =>
      guarded(async () => {
        const demo = reservasDemo();
        if (!has(demo, "offers")) return { items: [] };
        const [offers, c] = await Promise.all([demo.offers(), config()]);
        return { items: offers.map((o) => offerWire(o, c)) };
      }),
    own,
  ),
  route(
    "post",
    `${B}/offers/{offer_id}/stop`,
    200,
    ({ params }) =>
      guarded(async () => {
        const demo = reservasDemo();
        if (!has(demo, "stopOffer")) throw refuse(404, "not_found");
        return offerWire(await demo.stopOffer(params.offer_id), await config());
      }),
    own,
  ),
  route(
    "get",
    `${B}/slots`,
    200,
    ({ query }) =>
      guarded(async () => {
        const date = query.date ?? new Date().toISOString().slice(0, 10);
        const party = Number(query.party_size);
        const [slots, c] = await Promise.all([
          reservasDemo().freeSlots({
            date,
            ...(query.service_id ? { serviceId: query.service_id } : {}),
            ...(query.staff_id ? { proId: query.staff_id } : {}),
            ...(Number.isFinite(party) && party > 0 ? { partySize: party } : {}),
            // A reservation being moved: its own time counts as free (spec 069 R14.3).
            ...(query.exclude ? { exclude: query.exclude } : {}),
          }),
          config(),
        ]);
        return slotsOut(date, slots, c);
      }),
    own,
  ),
  route(
    "get",
    `${B}/occupancy`,
    200,
    ({ query }) =>
      guarded(async () => {
        const from = query.from ?? new Date().toISOString().slice(0, 10);
        const [o, c] = await Promise.all([reservasDemo().occupancy(from, query.to ?? from), config()]);
        return occupancyOut(o, c);
      }),
    own,
  ),
  route(
    "post",
    `${B}/walkins`,
    201,
    ({ json, headers }) =>
      guarded(async () => {
        const r = await reservasDemo().walkIn({ partySize: json?.party_size ?? 1, name: json?.name ?? null }, headers.get("Idempotency-Key") ?? `walkin-${Date.now()}`);
        return bookingOut(r, await config());
      }),
    own,
  ),
  route(
    "get",
    `${B}/waitlist`,
    200,
    () =>
      guarded(async () => {
        const [list, c] = await Promise.all([reservasDemo().waitlist(), config()]);
        return { enabled: c.waitlist.enabled, items: list.map((w) => entryOut(w, c)) };
      }),
    own,
  ),
  route(
    "post",
    `${B}/waitlist`,
    201,
    ({ json, headers }) =>
      guarded(async () => {
        const demo = reservasDemo();
        await demo.joinWaitlist(
          {
            partySize: json?.party_size ?? 1,
            name: json?.name ?? null,
            date: json?.date ?? new Date().toISOString().slice(0, 10),
            time: json?.time ? parseHHMM(json.time) : null,
            phone: json?.phone ?? null,
            inPerson: json?.in_person ?? !json?.phone,
            ...(json?.service_id ? { serviceId: json.service_id } : {}),
            ...(json?.staff_id ? { proId: json.staff_id } : {}),
            ...(json?.until ? { until: json.until } : {}),
          },
          headers.get("Idempotency-Key") ?? `wait-${Date.now()}`,
        );
        const [list, c] = await Promise.all([demo.waitlist(), config()]);
        const added = list.at(-1);
        if (!added) throw refuse(500, "error");
        return entryOut(added, c);
      }),
    own,
  ),
  route(
    "post",
    `${B}/waitlist/{entry_id}/offer`,
    200,
    ({ params }) =>
      guarded(async () => {
        const demo = reservasDemo();
        await demo.offer(params.entry_id);
        const [list, c] = await Promise.all([demo.waitlist(), config()]);
        const entry = list.find((w) => w.id === params.entry_id);
        if (!entry) throw refuse(404, "not_found");
        return offerOut(entry, c);
      }),
    own,
  ),
  route(
    "post",
    `${B}/waitlist/{entry_id}/remove`,
    204,
    ({ params }) =>
      guarded(async () => {
        await reservasDemo().removeWait(params.entry_id);
        return null;
      }),
    own,
  ),
  route(
    "get",
    `${B}/blocks`,
    200,
    ({ query }) =>
      guarded(async () => {
        const c = await reservasDemo().config();
        cached = c;
        const from = query.from ?? "";
        const to = query.to ?? "9999-12-31";
        return { items: (c.capacity?.blocks ?? []).filter((b) => b.date >= from && b.date <= to).map(blockOut) };
      }),
    own,
  ),
  route(
    "post",
    `${B}/blocks`,
    201,
    ({ json, headers }) =>
      guarded(async () => {
        const demo = reservasDemo();
        if (!json) throw refuse(422, "reason_required");
        await demo.block({ date: json.date, from: parseHHMM(json.from), until: parseHHMM(json.until), reason: json.label }, headers.get("Idempotency-Key") ?? `block-${Date.now()}`);
        const c = await demo.config();
        cached = c;
        const added = c.capacity?.blocks.at(-1);
        // Servicios has no blocks (043 §6): the example keeps none, and the API answers what it would have saved.
        const block = added ? blockOut(added) : { id: `b-${Date.now()}`, date: json.date, from: json.from, until: json.until, label: json.label, created_by_name: null };
        return { block, overlapping_bookings: 0 };
      }),
    own,
  ),
  route(
    "post",
    `${B}/blocks/{block_id}/remove`,
    204,
    ({ params }) =>
      guarded(async () => {
        await reservasDemo().unblock(params.block_id);
        cached = null;
        return null;
      }),
    own,
  ),
];
