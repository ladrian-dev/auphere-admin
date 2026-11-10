import type { Call } from "../backend";
import type { Day, Hours, Price, ShiftIn } from "./business-sections";

/**
 * Lane `reservas` (spec 043): the client's Reservas, all under
 * `/console/lite/reservas/*` (`contracts/lite-api.md` §2–§7, frozen on
 * 2026-10-22). No client reference travels: the API takes the client from the
 * verified person.
 *
 * Writes that create carry an `Idempotency-Key` (the screen keeps it across
 * retries of the same submit); writes that change a booking or the settings
 * carry `If-Match: <version>` and get a 412 `stale` when someone got there
 * first.
 */

export type ReservasMode = "services" | "capacity";
export type CapacityKind = "restaurant" | "bar" | "classes" | "tours" | "rooms" | "spa";
export const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
export type Weekday = (typeof WEEKDAYS)[number];
/** `HH:MM` local, in the business's time zone. */
export type TimeRange = { from: string; to: string };
/** Up to two ranges a day; an empty day is closed. */
export type WeekHours = Record<Weekday, TimeRange[]>;
/** ISO 4217 minor unit: CLP has none, so `amount_minor` is pesos. */
export type Money = { amount_minor: number; currency: string };

export type ConfirmationWhen = "24h" | "same_day_12" | "3h";
export type CapacityShift = { name: string; from: string; to: string };
export type CapacitySchedule =
  | { model: "shifts"; step_minutes: number; shifts: CapacityShift[] }
  /** `to` is the LAST arrival, included. */
  | { model: "slots"; step_minutes: number; from: string; to: string };
export type CapacitySettings = {
  seats: number;
  stay_minutes: number;
  max_party: number;
  walkin_hold: number;
  schedule: CapacitySchedule;
};

/** `GET /console/lite/reservas/settings`. */
export type ReservasSettings = {
  mode: ReservasMode;
  capacity_kind: CapacityKind | null;
  timezone: string;
  currency: string;
  /** Spec 055: si `currency` se sabe de verdad; si no, el modal pide elegirla. */
  currency_set?: boolean;
  /** The old projection (`monday: [{from, to}]`): closed days of the agenda and a person's «same as the business». */
  business_hours: WeekHours;
  business_hours_label: string | null;
  /** Spec 056 (5.1): the business's week in the ficha's shape — the one that is edited. */
  hours: Hours;
  /** Each location and whether it has its own hours: shown, never edited from here. */
  location_hours: LocationHours[];
  hours_missing: boolean;
  slot_step_minutes: number;
  waitlist: { enabled: boolean; lead_minutes: number };
  agent: { min_notice_minutes: number; max_days_ahead: number };
  confirmation: { enabled: boolean; when: ConfirmationWhen };
  reminder_enabled: boolean;
  release_unconfirmed: boolean;
  capacity: CapacitySettings | null;
  version: number;
};

/** `PATCH …/settings`: any subset of the editable fields (never `mode` nor `capacity_kind`). */
export type ReservasSettingsPatch = {
  waitlist?: Partial<ReservasSettings["waitlist"]>;
  agent?: Partial<ReservasSettings["agent"]>;
  confirmation?: Partial<ReservasSettings["confirmation"]>;
  reminder_enabled?: boolean;
  release_unconfirmed?: boolean;
  slot_step_minutes?: number;
  capacity?: Partial<CapacitySettings>;
};

export type LocationHours = { location: { id: string; name: string }; has_own_hours: boolean; label: string | null };
/**
 * `PATCH …/business-hours` (spec 056, 5.3): only the days that changed, with the
 * revision that was read. A 409 `revision_conflict` means someone saved meanwhile;
 * a 422 `{code, field, day}` says which day breaks which rule.
 */
export type BusinessHoursPatch = { revision: number; days: Partial<Record<Day, ShiftIn[]>> };

// ── §3 team and services (Servicios) ─────────────────────────────────────

export type StaffMember = {
  id: string;
  name: string;
  email: string | null;
  /** `null` = the business's hours. */
  hours: WeekHours | null;
  /** The hours that count. */
  effective_hours: WeekHours;
  position: number;
  archived: boolean;
  calendar: StaffCalendar;
  /** `no_hours`: their own week has no working day (R14.3). */
  warnings?: "no_hours"[];
};
/**
 * Spec 043, R12: each professional's own connection. `pending`: authorization asked for and
 * not finished. `needs_calendar`: connected, no calendar to use. `account`: which Google
 * account it ended up with. `last_error` is a code of ours (`connection`, `auth`,
 * `calendar_gone`, `read`, `write`, `calendar_in_use`, `no_calendar`, `new_account_refused`), never the provider's
 * text. `last_sync_at`: the last pass where everything worked.
 */
export type StaffCalendar = {
  status: "none" | "pending" | "connected" | "needs_calendar" | "needs_reauth" | "error";
  calendar_name?: string | null;
  account?: string | null;
  last_sync_at?: string | null;
  last_error?: string | null;
  /** Hours of theirs blocked by the business's Google calendar, until they connect their own. */
  business_busy?: boolean;
};
/** `GET …/staff/{id}/calendars`: that person's calendars one can write to. `used_by`: who else on the team has it. */
export type StaffCalendarOption = { id: string; name: string; primary: boolean; used_by: string | null };
export type StaffInput = { name: string; email: string | null; hours: WeekHours | null };
export type StaffPatch = Partial<StaffInput & { position: number }>;

export type ReservasService = {
  id: string;
  name: string;
  /** Spec 055: lo que lo agrupa; `null` es sin categoría. */
  category?: string | null;
  duration_minutes: number;
  /** Spec 056 (5.2): the ficha's price — none, free or an amount (`amount_minor`, minor units of `currency`). */
  price: Price;
  currency: string;
  staff: "all" | "some";
  staff_ids: string[];
  position: number;
  archived: boolean;
  /** `no_staff`: nobody active does it. `does_not_fit`: it doesn't fit the hours of those who do (R14). */
  warnings?: ("no_staff" | "does_not_fit")[];
};
/** `staff_ids: null` = the whole team. */
export type ServiceInput = { name: string; duration_minutes: number; price: Price; staff_ids: string[] | null; price_currency?: string; category?: string | null };
/**
 * Only what changed (spec 056, 5.3). `name` is accepted only if it is the one it
 * already has: Reservas does not rename (`422 rename_not_allowed`).
 */
export type ServicePatch = Partial<Omit<ServiceInput, "name"> & { position: number }>;

// ── §4 bookings ──────────────────────────────────────────────────────────

export type BookingStatus = "pending" | "confirmed" | "arrived" | "done" | "noshow" | "cancelled";
export type BookingOrigin = "agent" | "person" | "waitlist" | "walkin";
export type BookingChannel = "whatsapp" | "phone" | "in_person";
export type ActorKind = "agent" | "person" | "system";
export type BookingAction = "confirm" | "move" | "cancel" | "request_confirmation" | "arrive" | "noshow" | "undo";
/** The state transitions without a body (`POST …/{id}/<route>`). */
export type BookingTransition = "confirm" | "request_confirmation" | "arrive" | "noshow" | "undo";
export type LocalSpan = { date: string; start: string; end: string };

export type Booking = {
  id: string;
  mode: ReservasMode;
  status: BookingStatus;
  starts_at: string;
  ends_at: string;
  local: LocalSpan;
  party_size: number;
  staff: { id: string; name: string } | null;
  service: { id: string; name: string; duration_minutes: number } | null;
  price: Money | null;
  contact: { name: string | null; phone: string | null; conversation_id: string | null };
  origin: BookingOrigin;
  channel: BookingChannel;
  created_by: { kind: ActorKind; name: string | null };
  created_at: string;
  note: string | null;
  arrived_at: string | null;
  cancelled: { at: string; by: "customer" | "business" | "system"; cause: "mode_change" | "release_unconfirmed" | null } | null;
  wants_earlier: boolean;
  any_staff: boolean;
  late_minutes: number | null;
  clash: { source: "google"; local: { start: string; end: string } } | null;
  /** What the API accepts right now; the screen paints its buttons from here. */
  allowed: BookingAction[];
  version: number;
};

export type BookingEventKind =
  | "created"
  | "confirmed"
  | "confirmation_requested"
  | "reminder_sent"
  | "replied_yes"
  | "replied_no"
  | "moved"
  | "cancelled"
  | "arrived"
  | "noshow"
  | "undone"
  | "done"
  | "waitlist_joined"
  | "waitlist_accepted"
  | "notified"
  | "notify_failed"
  | "released";
export type BookingEvent = {
  kind: BookingEventKind;
  at: string;
  actor: { kind: ActorKind; name: string | null };
  data: Record<string, unknown>;
};
export type BookingDetail = Booking & { events: BookingEvent[] };

export type BookingsQuery = {
  from: string;
  to: string;
  status?: BookingStatus[];
  origin?: BookingOrigin[];
  staff_id?: string;
  q?: string;
};
export type BookingsPage = { items: Booking[]; closed_days: string[]; truncated: boolean };

export type CreateBookingInput = {
  date: string;
  time: string;
  staff_id?: string | null;
  service_id?: string | null;
  party_size?: number | null;
  contact: { name: string; phone: string | null };
  note: string | null;
  join_waitlist: boolean;
  notify: boolean;
};
/** `note` (enmienda 2026-10-22): sent only when it changes — absent leaves it, `null` clears it. */
export type MoveBookingInput = { date?: string; time?: string; staff_id?: string; party_size?: number; note?: string | null; notify: boolean };
export type CancelBookingInput = { notify: boolean; offer_slot: boolean };
export type CancelledBooking = Booking & { offer: { id: string; candidates: number } | null };
export type CancelPreview = {
  can_offer: boolean;
  candidates: number;
  why_not: "waitlist_off" | "too_soon" | "nobody_fits" | "not_services" | null;
};
export type WalkinInput = { party_size: number; name: string | null };

// ── §5 slots, occupancy, summary ─────────────────────────────────────────

export type SlotWhy = "past" | "blocked" | "full" | "closed" | "block_overlap";
export type ServicesSlots = { date: string; closed: boolean; slots: { time: string; staff_ids: string[] }[] };
export type CapacitySlot = { time: string; shift: string | null; fits: boolean; left: number; why: SlotWhy | null };
export type CapacitySlots = { date: string; closed: boolean; slots: CapacitySlot[]; first_fit: string | null };
export type ServicesSlotsQuery = { date: string; service_id: string; staff_id?: string; exclude?: string };
export type CapacitySlotsQuery = { date: string; party_size: number; walkin?: boolean; exclude?: string };

export type OccupancySlot = {
  time: string;
  shift: string | null;
  present: number;
  arriving: number;
  arrived: number;
  pending: number;
  blocked: { id: string; label: string } | null;
  past: boolean;
};
export type OccupancyDay = { date: string; closed: boolean; slots: OccupancySlot[] };
export type Occupancy = { seats: number; walkin_hold: number; stay_minutes: number; days: OccupancyDay[] };

export type ReservasSummary = {
  mode: ReservasMode;
  today: {
    date: string;
    bookings: number;
    confirmed: number;
    pending: number;
    next_at: string | null;
    people: number | null;
    inside_now: number | null;
    arriving_next_hour: number | null;
    /** Aforo: the business's seats («18 of 64 inside»). Servicios: null. */
    seats: number | null;
  } | null;
  week: { occupancy_pct: number | null; agent_share_pct: number | null } | null;
  month: { noshow_pct: number | null; recovered: number | null } | null;
  waitlist: { waiting: number } | null;
  clashes: number;
  upcoming: Booking[];
  errors?: string[];
};

// ── §6 blocks (Aforo) ────────────────────────────────────────────────────

export type ReservasBlock = { id: string; date: string; from: string; until: string; label: string; created_by_name: string | null };
export type BlockInput = { date: string; from: string; until: string; label: string };
export type BlockCreated = { block: ReservasBlock; overlapping_bookings: number };

// ── §7 waitlist and offers ───────────────────────────────────────────────

export type WaitlistEntry = {
  id: string;
  /** The contract names `waiting`; the Aforo design also draws `offered`, `accepted`, `removed`. */
  status: string;
  contact: { name: string | null; phone: string | null };
  party_size: number;
  desired: { date: string | null; time: string | null; until: string | null };
  service: { id: string; name: string; duration_minutes: number } | null;
  staff: { id: string; name: string } | null;
  booking_id: string | null;
  /** The booking they want earlier, where it is now (enmienda 2026-10-22); `null` without one. */
  booking_local: LocalSpan | null;
  joined: { kind: ActorKind | "in_person"; name: string | null; at: string };
  fits_now: boolean | null;
  offer: { id: string; deadline_at: string } | null;
};
export type WaitlistPage = { enabled: boolean; items: WaitlistEntry[] };
export type WaitlistQuery = { status?: string; from?: string; to?: string };
export type WaitlistInput =
  | { name: string; phone: string | null; party_size: number; date: string; time: string; in_person: boolean }
  | { name: string; phone: string | null; service_id: string; staff_id: string | null; date: string | null; until: string | null };

export type OfferCandidateStatus = "queued" | "waiting" | "noreply" | "accepted" | "late_taken" | "late_won" | "skipped" | "stopped";
export type SlotOffer = {
  id: string;
  /** The contract names `running`; anything else is a closed offer. */
  status: string;
  slot: {
    local: LocalSpan;
    staff: { id: string; name: string } | null;
    service: { id: string; name: string } | null;
    seats: number | null;
  };
  cancelled_by_name: string | null;
  window_minutes: number;
  candidates: {
    position: number;
    waitlist_id: string;
    name: string | null;
    status: OfferCandidateStatus;
    deadline_at: string | null;
    answered_at: string | null;
  }[];
  filled_booking_id: string | null;
  created_at: string;
};
export type OffersPage = { items: SlotOffer[] };

/** A query string where a list repeats its key (`status=a&status=b`). */
export function reservasQuery(params: Record<string, string | number | boolean | readonly string[] | null | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) for (const item of v) s.append(k, String(item));
    else s.set(k, String(v));
  }
  const out = s.toString();
  return out ? `?${out}` : "";
}

const R = "/console/lite/reservas";

export function reservasApi(call: Call) {
  const enc = encodeURIComponent;
  const ifMatch = (version: number) => ({ "If-Match": String(version) });
  const idem = (key: string) => ({ "Idempotency-Key": key });
  return {
    // §2 settings and hours
    reservasSettings: () => call<ReservasSettings>(`${R}/settings`),
    reservasPatchSettings: (body: ReservasSettingsPatch, version: number) =>
      call<ReservasSettings>(`${R}/settings`, { method: "PATCH", body, headers: ifMatch(version) }),
    reservasPatchBusinessHours: (body: BusinessHoursPatch) => call<Hours>(`${R}/business-hours`, { method: "PATCH", body }),

    // §3 team and services
    reservasStaff: (archived = false) => call<{ items: StaffMember[] }>(`${R}/staff${reservasQuery({ archived })}`),
    reservasCreateStaff: (body: StaffInput, key: string) =>
      call<StaffMember>(`${R}/staff`, { method: "POST", body, headers: idem(key) }),
    reservasUpdateStaff: (id: string, body: StaffPatch) =>
      call<StaffMember>(`${R}/staff/${enc(id)}`, { method: "PATCH", body }),
    reservasArchiveStaff: (id: string) => call<null>(`${R}/staff/${enc(id)}/archive`, { method: "POST" }),
    reservasServices: (archived = false) =>
      call<{ items: ReservasService[] }>(`${R}/services${reservasQuery({ archived })}`),
    reservasCreateService: (body: ServiceInput, key: string) =>
      call<ReservasService>(`${R}/services`, { method: "POST", body, headers: idem(key) }),
    reservasUpdateService: (id: string, body: ServicePatch) =>
      call<ReservasService>(`${R}/services/${enc(id)}`, { method: "PATCH", body }),
    reservasArchiveService: (id: string) => call<null>(`${R}/services/${enc(id)}/archive`, { method: "POST" }),

    // §8 each professional's calendar (R12)
    reservasConnectStaffCalendar: (id: string, share: boolean) =>
      call<{ redirect_url: string }>(`${R}/staff/${enc(id)}/calendar/connect`, { method: "POST", body: { share } }),
    reservasRefreshStaffCalendar: (id: string) => call<StaffMember>(`${R}/staff/${enc(id)}/calendar/refresh`, { method: "POST" }),
    reservasStaffCalendars: (id: string) => call<{ calendars: StaffCalendarOption[] }>(`${R}/staff/${enc(id)}/calendars`),
    reservasSetStaffCalendar: (id: string, calendarId: string | null) =>
      call<StaffMember>(`${R}/staff/${enc(id)}/calendar`, { method: "PUT", body: { calendar_id: calendarId } }),

    // §4 bookings
    reservasBookings: (p: BookingsQuery) => call<BookingsPage>(`${R}/bookings${reservasQuery(p)}`),
    reservasBooking: (id: string) => call<BookingDetail>(`${R}/bookings/${enc(id)}`),
    reservasCreateBooking: (body: CreateBookingInput, key: string) =>
      call<Booking>(`${R}/bookings`, { method: "POST", body, headers: idem(key) }),
    reservasMoveBooking: (id: string, body: MoveBookingInput, version: number) =>
      call<Booking>(`${R}/bookings/${enc(id)}/move`, { method: "POST", body, headers: ifMatch(version) }),
    reservasCancelBooking: (id: string, body: CancelBookingInput, version: number) =>
      call<CancelledBooking>(`${R}/bookings/${enc(id)}/cancel`, { method: "POST", body, headers: ifMatch(version) }),
    reservasCancelPreview: (id: string) => call<CancelPreview>(`${R}/bookings/${enc(id)}/cancel-preview`),
    reservasTransition: (id: string, action: BookingTransition, version: number) =>
      call<Booking>(`${R}/bookings/${enc(id)}/${action.replace("_", "-")}`, { method: "POST", headers: ifMatch(version) }),
    reservasWalkin: (body: WalkinInput, key: string) =>
      call<Booking>(`${R}/walkins`, { method: "POST", body, headers: idem(key) }),

    // §5 slots, occupancy, summary
    reservasServiceSlots: (p: ServicesSlotsQuery) => call<ServicesSlots>(`${R}/slots${reservasQuery(p)}`),
    reservasCapacitySlots: (p: CapacitySlotsQuery) => call<CapacitySlots>(`${R}/slots${reservasQuery(p)}`),
    reservasOccupancy: (from: string, to: string) => call<Occupancy>(`${R}/occupancy${reservasQuery({ from, to })}`),
    reservasSummary: () => call<ReservasSummary>(`${R}/summary`),

    // §6 blocks
    reservasBlocks: (from: string, to: string) =>
      call<{ items: ReservasBlock[] }>(`${R}/blocks${reservasQuery({ from, to })}`),
    reservasCreateBlock: (body: BlockInput, key: string) =>
      call<BlockCreated>(`${R}/blocks`, { method: "POST", body, headers: idem(key) }),
    reservasRemoveBlock: (id: string) => call<null>(`${R}/blocks/${enc(id)}/remove`, { method: "POST" }),

    // §7 waitlist and offers
    reservasWaitlist: (p: WaitlistQuery = {}) => call<WaitlistPage>(`${R}/waitlist${reservasQuery(p)}`),
    reservasAddWaitlist: (body: WaitlistInput, key: string) =>
      call<WaitlistEntry>(`${R}/waitlist`, { method: "POST", body, headers: idem(key) }),
    reservasRemoveWaitlist: (id: string) => call<null>(`${R}/waitlist/${enc(id)}/remove`, { method: "POST" }),
    reservasOfferWaitlist: (id: string) => call<SlotOffer>(`${R}/waitlist/${enc(id)}/offer`, { method: "POST" }),
    reservasOffers: (status: "running" | "recent") => call<OffersPage>(`${R}/offers${reservasQuery({ status })}`),
    reservasStopOffer: (id: string) => call<SlotOffer>(`${R}/offers/${enc(id)}/stop`, { method: "POST" }),
  };
}
