import { ApiError } from "@/api/errors";
import { addDays, type LocalDate } from "@/lib/reservas-model";

/**
 * Spec 069, Requisitos 14, 16 y 17: what the web already did, through the one
 * adapter (`api/reservas.ts`) and the example source the integrator looks at
 * (`reservas-demo.ts`). The wire is `schema.gen.ts`'s: `MoveIn`, `CancelIn`,
 * `CancelPreviewOut`, `OfferOut`, `SettingsPatchIn`, `WaitlistIn`.
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

const { httpSource, toReservation, toConfig } = require("@/api/reservas") as typeof import("@/api/reservas");
const { createDemo } = require("@/api/reservas-demo") as typeof import("@/api/reservas-demo");

beforeEach(() => {
  mockCalls.length = 0;
  mockReplies = [];
});

const wire = {
  id: "b1",
  mode: "services",
  status: "pending",
  local: { date: "2026-10-22", start: "16:30", end: "17:15" },
  staff: { id: "s1", name: "Lucía" },
  service: { id: "sv1", name: "Corte y barba", duration_minutes: 45 },
  price: { amount_minor: 15000, currency: "CLP" },
  contact: { name: "Ana Pérez", phone: "+56911112222", conversation_id: "c1" },
  origin: "agent",
  channel: "whatsapp",
  created_at: "2026-10-21T01:14:00Z",
  allowed: ["confirm", "move", "cancel", "request_confirmation"],
  version: 2,
};
const body = (i = 0) => JSON.parse(String(mockCalls[i]?.init?.body ?? "null")) as Record<string, unknown>;
const header = (i: number, name: string) => new Headers(mockCalls[i]?.init?.headers).get(name);

describe("the adapter (R14.1–R14.3, R16.2, R17.1)", () => {
  it("keeps «move» and «request_confirmation» from `allowed`, apart from the actions every screen names", () => {
    const r = toReservation(wire, "America/Santiago");
    expect(r.actions).toEqual(["confirm", "cancel"]);
    expect(r.moreActions).toEqual(["move", "request_confirmation"]);
  });

  it("reads the agent's notice and the reminders from the settings", () => {
    const c = toConfig({ mode: "services", agent: { min_notice_minutes: 240, max_days_ahead: 60 }, reminder_enabled: false, version: 1 }, [], [], null);
    expect(c.agent).toEqual({ minNoticeMin: 240 });
    expect(c.reminders).toBe(false);
    // Absent, the API's defaults: 60 minutes and reminders on.
    const d = toConfig({ mode: "services", version: 1 }, [], [], null);
    expect(d.agent).toEqual({ minNoticeMin: 60 });
    expect(d.reminders).toBe(true);
  });

  it("cancels with the person's choices: tell them or not, offer the slot or not", async () => {
    mockReplies = [{ status: 200, body: { ...wire, status: "cancelled", allowed: [] } }];
    const r = await httpSource().cancel({ id: "b1", version: 2 }, { notify: false, offerSlot: true });
    expect(mockCalls[0]?.url).toMatch(/\/console\/lite\/reservas\/bookings\/b1\/cancel$/);
    expect(body()).toEqual({ notify: false, offer_slot: true });
    expect(header(0, "If-Match")).toBe("2");
    expect(r.state).toBe("cancelled");
  });

  it("asks whether the slot can go to the waitlist", async () => {
    mockReplies = [{ status: 200, body: { can_offer: true, candidates: 3, why_not: null } }];
    expect(await httpSource().cancelPreview("b1")).toEqual({ canOffer: true, candidates: 3, whyNot: null });
    expect(mockCalls[0]?.url).toMatch(/\/bookings\/b1\/cancel-preview$/);
  });

  it("moves to a day and a time, with whom and whether to tell them, with its version", async () => {
    mockReplies = [{ status: 200, body: { ...wire, local: { date: "2026-10-23", start: "10:00", end: "10:45" } } }];
    const r = await httpSource().move({ id: "b1", version: 2 }, { date: "2026-10-23", time: 600, proId: "s1", notify: true });
    expect(mockCalls[0]?.url).toMatch(/\/bookings\/b1\/move$/);
    expect(body()).toEqual({ date: "2026-10-23", time: "10:00", staff_id: "s1", notify: true });
    expect(header(0, "If-Match")).toBe("2");
    expect(r.date).toBe("2026-10-23");
  });

  it("asks the customer to confirm", async () => {
    mockReplies = [{ status: 200, body: wire }];
    await httpSource().requestConfirmation({ id: "b1", version: 2 });
    expect(mockCalls[0]?.url).toMatch(/\/bookings\/b1\/request-confirmation$/);
    expect(mockCalls[0]?.init?.method).toBe("POST");
    expect(header(0, "If-Match")).toBe("2");
  });

  it("reads the running offers and stops one", async () => {
    const offer = {
      id: "o1",
      status: "running",
      created_at: "2026-10-22T13:00:00Z",
      window_minutes: 5,
      cancelled_by_name: "Ana",
      filled_booking_id: null,
      slot: { local: { date: "2026-10-22", start: "16:00", end: "16:30" }, seats: null, service: { id: "s", name: "Corte" }, staff: { id: "p", name: "Javiera" } },
      candidates: [
        { waitlist_id: "w2", name: "Cristóbal", position: 2, status: "queued", deadline_at: null, answered_at: null },
        { waitlist_id: "w1", name: "Florencia", position: 1, status: "waiting", deadline_at: "2026-10-22T13:05:00Z", answered_at: null },
      ],
    };
    mockReplies = [{ status: 200, body: { items: [offer] } }, { status: 200, body: { ...offer, status: "stopped" } }];
    const list = await httpSource().offers();
    expect(mockCalls[0]?.url).toMatch(/\/offers\?status=running$/);
    expect(list[0]).toMatchObject({ id: "o1", status: "running", slot: { date: "2026-10-22", start: 960, service: "Corte", pro: "Javiera" } });
    expect(list[0]?.candidates.map((c) => c.name)).toEqual(["Florencia", "Cristóbal"]);
    expect((await httpSource().stopOffer("o1")).status).toBe("stopped");
    expect(mockCalls[1]?.url).toMatch(/\/offers\/o1\/stop$/);
  });

  it("saves the agent's notice and the reminders", async () => {
    mockReplies = [{ status: 200, body: {} }, { status: 200, body: { mode: "capacity", version: 5 } }, { status: 200, body: { items: [] } }];
    await httpSource().patchConfig({ agent: { minNoticeMin: 1440 }, reminders: false }, 4);
    expect(body()).toEqual({ agent: { min_notice_minutes: 1440 }, reminder_enabled: false });
  });

  it("puts someone on the waitlist by hand with their phone and what they want; at the door, without", async () => {
    mockReplies = [{ status: 201, body: {} }, { status: 201, body: {} }];
    await httpSource().joinWaitlist({ partySize: 1, name: "Ana", phone: "+56 9 1111 2222", inPerson: false, date: null, time: null, serviceId: "sv1", proId: null, until: "2026-10-29" }, "k1");
    expect(body(0)).toEqual({ name: "Ana", phone: "+56 9 1111 2222", party_size: 1, date: null, time: null, in_person: false, service_id: "sv1", until: "2026-10-29" });
    await httpSource().joinWaitlist({ partySize: 2, name: null, date: "2026-10-22", time: 780 }, "k2");
    expect(body(1)).toMatchObject({ phone: null, in_person: true, time: "13:00" });
  });

  it("asks for the slots of a reservation being moved without counting it", async () => {
    mockReplies = [{ status: 200, body: { mode: "services", version: 1 } }, { status: 200, body: { items: [] } }, { status: 200, body: { items: [] } }, { status: 200, body: { closed: false, slots: [] } }];
    await httpSource().freeSlots({ date: "2026-10-23", serviceId: "sv1", exclude: "b1" });
    expect(mockCalls.at(-1)?.url).toMatch(/\/slots\?date=2026-10-23&service_id=sv1&exclude=b1$/);
  });
});

jest.useFakeTimers({ doNotFake: ["Date"] });
const run = async <T,>(p: Promise<T>): Promise<T> => {
  const settled = p.then(
    (value) => ({ ok: true as const, value }),
    (error: unknown) => ({ ok: false as const, error }),
  );
  await jest.advanceTimersByTimeAsync(3000);
  const r = await settled;
  if (r.ok) return r.value;
  throw r.error;
};

describe("the example source serves the new actions (R23, for the integrator)", () => {
  /** A pending reservation ahead, with a phone, of the example's next days. */
  async function pendingAhead(demo: ReturnType<typeof createDemo>) {
    const c = await run(demo.config());
    const today = (await run(demo.range("2000-01-01", "2000-01-01"))).now.date as LocalDate;
    const r = await run(demo.range(today, addDays(today, 6)));
    return { c, today, items: r.items };
  }

  it("each calendar in its real state, the agent's notice and the reminders", async () => {
    const demo = createDemo("services", null);
    const c = await run(demo.config());
    expect(c.services?.team.map((p) => p.calendarState ?? (p.calendar === "google" ? "connected" : "none"))).toEqual(["connected", "connected", "pending"]);
    expect(c.services?.team[2]?.calendarBusy).toBe(true);
    expect(c.agent?.minNoticeMin).toBe(60);
    const next = await run(demo.patchConfig({ agent: { minNoticeMin: 120 }, reminders: false }, c.version));
    expect(next.agent?.minNoticeMin).toBe(120);
    expect(next.reminders).toBe(false);
  });

  it("moves a reservation to a free slot, and refuses one that is taken", async () => {
    const demo = createDemo("services", null);
    const { today, items } = await pendingAhead(demo);
    const r = items.find((x) => x.moreActions?.includes("move") && x.date > today);
    expect(r).toBeTruthy();
    // The first later day with room for the same service and person (Sunday is closed).
    let tomorrow = r!.date;
    let slot: Awaited<ReturnType<typeof demo.freeSlots>>[number] | undefined;
    for (let i = 1; i <= 7 && !slot; i++) {
      tomorrow = addDays(r!.date, i);
      slot = (await run(demo.freeSlots({ date: tomorrow, serviceId: r!.service!.id, proId: r!.pro!.id, exclude: r!.id })))[0];
    }
    expect(slot).toBeTruthy();
    const moved = await run(demo.move(r!, { date: tomorrow, time: slot!.time, proId: r!.pro!.id, notify: true }));
    expect(moved).toMatchObject({ date: tomorrow, start: slot!.time });
    // "notified" only follows when the customer has a phone, and the demo draws that from
    // the date: on some days the moved reservation has none and "created" sits second to last.
    expect(moved.events.filter((e) => e.kind !== "notified").at(-1)?.kind).toBe("moved");
    await expect(run(demo.move(moved, { date: tomorrow, time: 0, notify: false }))).rejects.toBeInstanceOf(ApiError);
  });

  it("asks a pending one to confirm, once per half hour", async () => {
    const demo = createDemo("services", null);
    const { items } = await pendingAhead(demo);
    const r = items.find((x) => x.moreActions?.includes("request_confirmation"));
    expect(r).toBeTruthy();
    const asked = await run(demo.requestConfirmation(r!));
    expect(asked.events.at(-1)?.kind).toBe("confirmation_requested");
    expect(asked.moreActions).not.toContain("request_confirmation");
  });

  it("previews and cancels with the slot offered to the waitlist, which then shows a running offer", async () => {
    const demo = createDemo("services", null);
    const { items } = await pendingAhead(demo);
    const before = (await run(demo.offers())).length;
    // Florencia waits for «Corte y peinado» with Marcos: Lucía's 17:00 on the next open day fits her.
    const lucia = items.find((x) => x.customer.name === "Lucía Fernández")!;
    expect(await run(demo.cancelPreview(lucia.id))).toEqual({ canOffer: true, candidates: 1, whyNot: null });
    const cancelled = await run(demo.cancel(lucia, { notify: true, offerSlot: true }));
    expect(cancelled.state).toBe("cancelled");
    const offers = await run(demo.offers());
    expect(offers).toHaveLength(before + 1);
    expect(offers[0]?.candidates[0]?.name).toBe("Florencia Araya");
    const stopped = await run(demo.stopOffer(offers[0]!.id));
    expect(stopped.status).toBe("stopped");
    expect(await run(demo.offers())).toHaveLength(before);
  });

  it("puts someone on the waitlist by hand only with a phone", async () => {
    const demo = createDemo("services", null);
    await expect(run(demo.joinWaitlist({ partySize: 1, name: "Ana", phone: null, inPerson: false, date: null, time: null, serviceId: "s-corte" }, "k"))).rejects.toBeInstanceOf(ApiError);
    await run(demo.joinWaitlist({ partySize: 1, name: "Ana Pérez", phone: "+56 9 1111 2222", inPerson: false, date: null, time: null, serviceId: "s-corte", until: "2099-01-01" }, "k2"));
    const list = await run(demo.waitlist());
    expect(list.at(-1)).toMatchObject({ name: "Ana Pérez", phone: "+56 9 1111 2222", wants: { service: "Corte" } });
  });
});
