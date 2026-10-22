import type {
  Booking,
  BookingDetail,
  OccupancyDay,
  ReservasService,
  ReservasSettings,
  SlotOffer,
  StaffMember,
  WaitlistEntry,
  WeekHours,
} from "@/lib/backend/reservas";

/**
 * Fixtures built from the shapes of `contracts/lite-api.md` (spec 043). Chile:
 * CLP, +56. Today is Thursday 2026-10-22 and «now» 16:40 in Santiago.
 */
export const TODAY = "2026-10-22";
export const NOW_MIN = 16 * 60 + 40;
export const NOW_ISO = "2026-10-22T19:40:00Z";

let seq = 0;
/** A deterministic UUID: the same fixture order gives the same ids. */
export function uid(): string {
  seq += 1;
  return `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`;
}

const split = [
  { from: "09:00", to: "14:00" },
  { from: "15:00", to: "19:00" },
];

export function weekHours(o: Partial<WeekHours> = {}): WeekHours {
  return {
    monday: split,
    tuesday: split,
    wednesday: split,
    thursday: split,
    friday: split,
    saturday: [{ from: "10:00", to: "14:00" }],
    sunday: [],
    ...o,
  };
}

export const LUCIA = "00000000-0000-4000-8000-0000000000a1";
export const MARCOS = "00000000-0000-4000-8000-0000000000a2";
export const CORTE = "00000000-0000-4000-8000-0000000000b1";
export const BARBA = "00000000-0000-4000-8000-0000000000b2";

export function servicesSettings(o: Partial<ReservasSettings> = {}): ReservasSettings {
  return {
    mode: "services",
    capacity_kind: null,
    timezone: "America/Santiago",
    currency: "CLP",
    business_hours: weekHours(),
    business_hours_label: "Lunes a viernes 9:00–19:00",
    hours_missing: false,
    slot_step_minutes: 30,
    waitlist: { enabled: true, lead_minutes: 120 },
    agent: { min_notice_minutes: 60, max_days_ahead: 60 },
    confirmation: { enabled: true, when: "24h" },
    reminder_enabled: true,
    release_unconfirmed: false,
    capacity: null,
    version: 4,
    ...o,
  };
}

export function capacitySettings(o: Partial<ReservasSettings> = {}): ReservasSettings {
  return {
    ...servicesSettings(),
    mode: "capacity",
    capacity_kind: "restaurant",
    business_hours: weekHours({
      monday: [{ from: "13:00", to: "23:00" }],
      tuesday: [{ from: "13:00", to: "23:00" }],
      wednesday: [{ from: "13:00", to: "23:00" }],
      thursday: [{ from: "13:00", to: "23:00" }],
      friday: [{ from: "13:00", to: "23:00" }],
      saturday: [{ from: "13:00", to: "23:00" }],
      sunday: [{ from: "13:00", to: "16:00" }],
    }),
    confirmation: { enabled: true, when: "24h" },
    release_unconfirmed: true,
    capacity: {
      seats: 64,
      stay_minutes: 90,
      max_party: 10,
      walkin_hold: 6,
      schedule: {
        model: "shifts",
        step_minutes: 30,
        shifts: [
          { name: "Comida", from: "13:00", to: "15:00" },
          { name: "Cena", from: "20:00", to: "22:00" },
        ],
      },
    },
    ...o,
  };
}

export function staff(o: Partial<StaffMember> = {}): StaffMember {
  return {
    id: LUCIA,
    name: "Lucía",
    email: null,
    hours: null,
    effective_hours: weekHours(),
    position: 1,
    archived: false,
    calendar: { status: "none" },
    ...o,
  };
}

export function service(o: Partial<ReservasService> = {}): ReservasService {
  return {
    id: CORTE,
    name: "Corte y barba",
    duration_minutes: 45,
    price: { amount_minor: 15000, currency: "CLP" },
    staff: "all",
    staff_ids: [],
    position: 1,
    archived: false,
    ...o,
  };
}

export function booking(o: Partial<Booking> = {}): Booking {
  return {
    id: uid(),
    mode: "services",
    status: "confirmed",
    starts_at: "2026-10-22T19:30:00Z",
    ends_at: "2026-10-22T20:15:00Z",
    local: { date: TODAY, start: "16:30", end: "17:15" },
    party_size: 1,
    staff: { id: LUCIA, name: "Lucía" },
    service: { id: CORTE, name: "Corte y barba", duration_minutes: 45 },
    price: { amount_minor: 15000, currency: "CLP" },
    contact: { name: "Ana Pérez", phone: "+56911112222", conversation_id: null },
    origin: "agent",
    channel: "whatsapp",
    created_by: { kind: "agent", name: "Agente de reservas" },
    created_at: "2026-10-22T01:14:00Z",
    note: null,
    arrived_at: null,
    cancelled: null,
    wants_earlier: false,
    any_staff: false,
    late_minutes: null,
    clash: null,
    allowed: ["confirm", "move", "cancel", "request_confirmation"],
    version: 2,
    ...o,
  };
}

export function capacityBooking(o: Partial<Booking> = {}): Booking {
  return booking({
    mode: "capacity",
    local: { date: TODAY, start: "20:30", end: "22:00" },
    party_size: 4,
    staff: null,
    service: null,
    price: null,
    allowed: ["arrive", "move", "cancel"],
    ...o,
  });
}

export function detail(o: Partial<BookingDetail> = {}): BookingDetail {
  return { ...booking(), events: [], ...o };
}

export function occupancyDay(date: string, o: Partial<OccupancyDay> = {}): OccupancyDay {
  const times = ["13:00", "13:30", "14:00", "14:30", "15:00", "20:00", "20:30", "21:00", "21:30", "22:00"];
  return {
    date,
    closed: false,
    slots: times.map((time) => ({
      time,
      shift: time < "16:00" ? "Comida" : "Cena",
      present: 0,
      arriving: 0,
      arrived: 0,
      pending: 0,
      blocked: null,
      past: false,
    })),
    ...o,
  };
}

export function waitlistEntry(o: Partial<WaitlistEntry> = {}): WaitlistEntry {
  return {
    id: uid(),
    status: "waiting",
    contact: { name: "Marta Gil", phone: "+56922223333" },
    party_size: 2,
    desired: { date: "2026-10-23", time: "20:30", until: null },
    service: null,
    staff: null,
    booking_id: null,
    booking_local: null,
    joined: { kind: "agent", name: null, at: "2026-10-22T13:12:00Z" },
    fits_now: true,
    offer: null,
    ...o,
  };
}

export function offer(o: Partial<SlotOffer> = {}): SlotOffer {
  return {
    id: uid(),
    status: "running",
    slot: {
      local: { date: TODAY, start: "17:30", end: "18:15" },
      staff: { id: LUCIA, name: "Lucía" },
      service: { id: CORTE, name: "Corte y barba" },
      seats: null,
    },
    cancelled_by_name: "Ana Pérez",
    window_minutes: 5,
    candidates: [
      { position: 1, waitlist_id: uid(), name: "Marta Gil", status: "noreply", deadline_at: null, answered_at: null },
      { position: 2, waitlist_id: uid(), name: "Pedro Soto", status: "waiting", deadline_at: "2026-10-22T19:44:59Z", answered_at: null },
      { position: 3, waitlist_id: uid(), name: "Rosa Díaz", status: "queued", deadline_at: null, answered_at: null },
    ],
    filled_booking_id: null,
    created_at: "2026-10-22T19:35:00Z",
    ...o,
  };
}
