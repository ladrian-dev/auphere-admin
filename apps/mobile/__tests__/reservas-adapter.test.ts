import { ApiError } from "@/api/errors";

/**
 * Spec 044, research D1, T047: the one place that knows the API's contract —
 * `specs/043-reservas/contracts/lite-api.md`, frozen 2026-10-22. It turns the
 * wire into the model and the API's refusals into codes the screens say in
 * one sentence. The JSON here is the contract's own examples.
 */
const mockCalls: { url: string; init: RequestInit | undefined }[] = [];
let mockReplies: { status: number; body: unknown }[] = [];

jest.mock("@/api/client", () => ({
  authedFetch: jest.fn(async (url: string, init?: RequestInit) => {
    mockCalls.push({ url, init });
    const r = mockReplies.shift() ?? { status: 200, body: {} };
    return new Response(r.status === 204 ? null : JSON.stringify(r.body), { status: r.status, headers: { "Content-Type": "application/json" } });
  }),
}));

const { httpSource, toConfig, toReservation } = require("@/api/reservas") as typeof import("@/api/reservas");

beforeEach(() => {
  mockCalls.length = 0;
  mockReplies = [];
});

/** 043 §4 «El objeto Booking». */
const booking = {
  id: "b1",
  mode: "services",
  status: "pending",
  starts_at: "2026-10-22T19:30:00Z",
  ends_at: "2026-10-22T20:15:00Z",
  local: { date: "2026-10-22", start: "16:30", end: "17:15" },
  party_size: 1,
  staff: { id: "s1", name: "Lucía" },
  service: { id: "sv1", name: "Corte y barba", duration_minutes: 45 },
  price: { amount_minor: 15000, currency: "CLP" },
  contact: { name: "Ana Pérez", phone: "+56911112222", conversation_id: "c1" },
  origin: "agent",
  channel: "whatsapp",
  created_by: { kind: "agent", name: "Agente de reservas" },
  created_at: "2026-10-21T01:14:00Z",
  note: "Pidió con Lucía",
  arrived_at: null,
  cancelled: null,
  wants_earlier: false,
  any_staff: false,
  late_minutes: null,
  clash: null,
  allowed: ["confirm", "move", "cancel", "request_confirmation"],
  version: 2,
};

/** 043 §2 «GET /settings». */
const settings = {
  mode: "capacity",
  capacity_kind: "restaurant",
  timezone: "America/Santiago",
  currency: "CLP",
  business_hours: {
    monday: [{ from: "13:00", to: "23:00" }],
    tuesday: [{ from: "13:00", to: "23:00" }],
    wednesday: [{ from: "13:00", to: "23:00" }],
    thursday: [{ from: "13:00", to: "23:00" }],
    friday: [{ from: "13:00", to: "23:00" }],
    saturday: [{ from: "13:00", to: "23:00" }],
    sunday: [{ from: "13:00", to: "16:00" }],
  },
  business_hours_label: "Lunes a sábado 13:00–23:00",
  hours_missing: false,
  slot_step_minutes: 30,
  waitlist: { enabled: true, lead_minutes: 120 },
  agent: { min_notice_minutes: 60, max_days_ahead: 60 },
  confirmation: { enabled: true, when: "24h" },
  reminder_enabled: true,
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
  version: 4,
};

describe("the contract into the model", () => {
  it("reads a booking in the business's wall time, with only the actions the phone offers", () => {
    const r = toReservation(booking, "America/Santiago");
    expect(r).toMatchObject({ id: "b1", version: 2, date: "2026-10-22", start: 16 * 60 + 30, end: 17 * 60 + 15, state: "pending" });
    expect(r.service).toEqual({ id: "sv1", name: "Corte y barba", durationMin: 45, price: 15000 });
    expect(r.pro).toEqual({ id: "s1", name: "Lucía" });
    expect(r.partySize).toBeNull(); // Servicios: party size means nothing
    expect(r.customer).toEqual({ name: "Ana Pérez", phone: "+56911112222", conversationId: "c1" });
    expect(r.actions).toEqual(["confirm", "cancel"]); // move and request_confirmation are not on the phone yet
  });

  it("maps `arrive` to «Llegó», keeps the API's lateness, and says the arrival in local time", () => {
    const r = toReservation(
      { ...booking, mode: "capacity", status: "arrived", party_size: 4, staff: null, service: null, price: null, arrived_at: "2026-10-22T16:04:00Z", late_minutes: null, allowed: ["undo"] },
      "America/Santiago",
    );
    expect(r.partySize).toBe(4);
    expect(r.arrivedLocal).toBe("13:04");
    expect(r.actions).toEqual(["undo"]);
    expect(toReservation({ ...booking, allowed: ["arrive", "noshow"], late_minutes: 20 }, "America/Santiago")).toMatchObject({ actions: ["arrived", "noshow"], lateMinutes: 20 });
  });

  it("a walk-in without a name has an empty one (the screen says «Sin nombre»)", () => {
    expect(toReservation({ ...booking, origin: "walkin", contact: { name: null, phone: null } }, "America/Santiago").customer.name).toBe("");
  });

  it("never invents a channel the app does not show (only WhatsApp by Meta, phone, in the place)", () => {
    expect(toReservation({ ...booking, channel: "instagram" }, "America/Santiago").channel).toBe("whatsapp");
    expect(toReservation({ ...booking, channel: "phone" }, "America/Santiago").channel).toBe("phone");
  });

  it("reads Aforo's settings: shifts, the four numbers, the version, and the shifts closed by the hours", () => {
    const c = toConfig(settings, null, null, [{ id: "k1", date: "2026-10-24", from: "20:00", until: "22:00", label: "Cena de empresa" }]);
    expect(c).toMatchObject({ mode: "capacity", version: 4, hoursLabel: "Lunes a sábado 13:00–23:00" });
    expect(c.hours[0]).toEqual({ weekday: 1, open: 780, close: 1380 });
    expect(c.waitlist.leadHours).toBe(2);
    expect(c.capacity).toMatchObject({ capacity: 64, stayMin: 90, maxParty: 10, walkinReserved: 6 });
    expect(c.capacity?.shifts).toEqual([
      { name: "Comida", from: 780, to: 900, everyMin: 30 },
      { name: "Cena", from: 1200, to: 1320, everyMin: 30 },
    ]);
    // Sunday 13:00–16:00 covers lunch and not dinner.
    expect(c.capacity?.closed).toEqual([{ weekday: 7, shift: "Cena" }]);
    expect(c.capacity?.blocks[0]).toEqual({ id: "k1", date: "2026-10-24", from: 1200, until: 1320, reason: "Cena de empresa", shift: "Cena" });
  });

  it("reads Servicios' team and services, with prices in CLP", () => {
    const c = toConfig(
      { ...settings, mode: "services", capacity_kind: null, capacity: null },
      [{ id: "s1", name: "Lucía", calendar: { status: "connected" } }],
      [{ id: "sv1", name: "Corte y barba", duration_minutes: 45, price: { amount_minor: 15000, currency: "CLP" }, staff: "some", staff_ids: ["s1"] }],
      null,
    );
    expect(c.services?.team).toEqual([{ id: "s1", name: "Lucía", calendar: "google" }]);
    expect(c.services?.catalog).toEqual([{ id: "sv1", name: "Corte y barba", durationMin: 45, price: 15000, proIds: ["s1"] }]);
  });
});

describe("the HTTP source", () => {
  it("asks for the bookings of a range under /reservas", async () => {
    mockReplies = [{ status: 200, body: { items: [booking], closed_days: [], truncated: false } }];
    const range = await httpSource().range("2026-10-22", "2026-10-22");
    expect(mockCalls[0]?.url).toMatch(/\/console\/lite\/reservas\/bookings\?from=2026-10-22&to=2026-10-22$/);
    expect(range.items).toHaveLength(1);
    expect(range.now.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("sends a new booking once, with its idempotency key, the time as HH:MM and «notify»", async () => {
    mockReplies = [{ status: 201, body: booking }];
    await httpSource().create({ date: "2026-10-23", time: 17 * 60, customer: { name: "Lucía Fernández", phone: null }, serviceId: "sv1", proId: "s1" }, "key-1");
    const init = mockCalls[0]?.init;
    expect(mockCalls[0]?.url).toMatch(/\/console\/lite\/reservas\/bookings$/);
    expect((init?.headers as Record<string, string>)["Idempotency-Key"]).toBe("key-1");
    expect(JSON.parse(String(init?.body))).toEqual({
      date: "2026-10-23",
      time: "17:00",
      service_id: "sv1",
      staff_id: "s1",
      contact: { name: "Lucía Fernández", phone: null },
      note: null,
      join_waitlist: false,
      notify: true,
    });
  });

  it("acts with the booking's version in If-Match, under the API's action names", async () => {
    mockReplies = [{ status: 200, body: booking }];
    await httpSource().act({ id: "b1", version: 2 }, "arrived");
    expect(mockCalls[0]?.url).toMatch(/\/reservas\/bookings\/b1\/arrive$/);
    expect((mockCalls[0]?.init?.headers as Record<string, string>)["If-Match"]).toBe("2");
  });

  it("cancels telling the customer (clarification 2)", async () => {
    mockReplies = [{ status: 200, body: { ...booking, status: "cancelled" } }];
    await httpSource().act({ id: "b1", version: 2 }, "cancel");
    expect(mockCalls[0]?.url).toMatch(/\/bookings\/b1\/cancel$/);
    expect(JSON.parse(String(mockCalls[0]?.init?.body))).toEqual({ notify: true });
  });

  it.each([
    [412, "stale"],
    [409, "invalid_transition"],
    [409, "slot_taken"],
  ])("turns a %i %s into an ApiError with its code", async (status, code) => {
    mockReplies = [{ status, body: { detail: { code } } }];
    await expect(httpSource().act({ id: "b1", version: 2 }, "confirm")).rejects.toMatchObject({ code });
    mockReplies = [{ status, body: { detail: { code } } }];
    await expect(httpSource().act({ id: "b1", version: 2 }, "confirm")).rejects.toBeInstanceOf(ApiError);
  });

  it("a walk-in that does not fit is «no_room», and outside service «closed» (043 §4)", async () => {
    mockReplies = [{ status: 409, body: { detail: { code: "slot_taken", first_fit: null } } }];
    await expect(httpSource().walkIn({ partySize: 30, name: null }, "k")).rejects.toMatchObject({ code: "no_room" });
    mockReplies = [{ status: 409, body: { detail: { code: "invalid_transition", next_time: "20:00" } } }];
    await expect(httpSource().walkIn({ partySize: 2, name: null }, "k")).rejects.toMatchObject({ code: "closed" });
  });
});
