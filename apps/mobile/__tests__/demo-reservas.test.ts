import { demoIds, resetDemo } from "@/api/demo";
import { ApiError } from "@/api/errors";
import type { Reservation, WaitEntry } from "@/api/reservas";
import { reservasDemo } from "@/api/demo/reservas";
import { createDemo } from "@/api/reservas-demo";
import * as model from "@/lib/reservas-model";

/**
 * Spec 069, Requisito 23, with spec 044's example: in the example API,
 * Reservas is the example source of `reservas-demo.ts` written in the wire.
 * Read back through the app's own adapter (`httpSource`, `toConfig`,
 * `toReservation`, `toWaitEntry`) it holds everything the source gives — so
 * a wrong field or action name here shows as a difference, not as a type.
 * (The adapter may read more than the example keeps — spec 069 adds fields —
 * so the comparison is «contains», not «equals».)
 */
jest.mock("@/api/client", () => ({
  authedFetch: (input: Request | string, init?: RequestInit) =>
    (jest.requireActual("@/api/demo") as typeof import("@/api/demo")).demoFetch(input, init),
}));

const { httpSource } = require("@/api/reservas") as typeof import("@/api/reservas");

jest.useFakeTimers({ now: new Date("2026-11-17T14:30:00Z") });

async function run<T>(p: Promise<T>): Promise<T> {
  const settled = p.then(
    (value) => ({ ok: true as const, value }),
    (error: unknown) => ({ ok: false as const, error }),
  );
  await jest.advanceTimersByTimeAsync(3000);
  const r = await settled;
  if (r.ok) return r.value;
  throw r.error;
}

beforeEach(() => resetDemo());

const FROM = "2026-11-17";
const TO = "2026-11-23";

const MADE_UP = /^\+34 600 000 0\d\d$/;

/**
 * The wire says «no conversation» as `null`; the example leaves it out. Its
 * numbers go out as this example's (`+34 600 000 0xx`), checked apart.
 */
function plain(r: Reservation): Reservation {
  const { conversationId, ...customer } = r.customer;
  return { ...r, customer: { ...(conversationId ? { ...customer, conversationId } : customer), phone: r.customer.phone ? "phone" : null } };
}

/** A list carries no history (043 §4). */
function listed(r: Reservation): Reservation {
  return { ...plain(r), events: [] };
}

/** What the wire cannot carry for Servicios: a party (it says 1), a free-text wish, an «until» it did not set. */
function waited(w: WaitEntry): WaitEntry {
  return { ...w, phone: w.phone ? "phone" : null, wants: { ...w.wants, partySize: null, text: null, until: w.wants.until ?? null } };
}

describe("the example business's clock (spec 069, R23)", () => {
  it("is the business's wall clock, the one the app reads, not a fixed 11:20", async () => {
    const http = httpSource();
    await run(http.config());
    const wire = await run(http.range(FROM, FROM));
    const direct = await run(reservasDemo().range(FROM, FROM));
    // 14:30 UTC is 11:30 in Santiago: the app reads it, and the example agrees.
    expect(wire.now).toMatchObject({ date: FROM, minutes: 11 * 60 + 30 });
    expect(direct.now).toMatchObject({ date: wire.now.date, minutes: wire.now.minutes });
  });

  it("no history is in the future: made, asked, answered or cancelled before now, early in the morning too", async () => {
    // 05:10 in Santiago: the day's bookings are all to come.
    jest.setSystemTime(new Date("2026-11-17T08:10:00Z"));
    resetDemo();
    try {
      const { items } = await run(reservasDemo().range(FROM, TO));
      expect(items.length).toBeGreaterThan(20);
      for (const r of items) {
        expect({ id: r.id, made: Date.parse(r.createdAt) <= Date.now() }).toEqual({ id: r.id, made: true });
        for (const e of r.events) expect({ id: r.id, kind: e.kind, past: Date.parse(e.at) <= Date.now() }).toEqual({ id: r.id, kind: e.kind, past: true });
      }
    } finally {
      jest.setSystemTime(new Date("2026-11-17T14:30:00Z"));
      resetDemo();
    }
  });

  it("Lucía's booking is on the next open day, a Saturday too (the Sunday is closed)", async () => {
    // Saturday 21, 09:00 in Santiago.
    jest.setSystemTime(new Date("2026-11-21T12:00:00Z"));
    try {
      const demo = createDemo("services", null);
      const c = await run(demo.config());
      const { items } = await run(demo.range("2026-11-21", "2026-11-27"));
      const lucia = items.find((r) => r.customer.name === "Lucía Fernández");
      expect(lucia?.date).toBe("2026-11-23");
      expect(model.isClosed(c, "2026-11-22")).toBe(true);
    } finally {
      jest.setSystemTime(new Date("2026-11-17T14:30:00Z"));
    }
  });

  it("so nothing still to come is already served, and nothing past is still to come", async () => {
    const { items, now } = await run(reservasDemo().range(FROM, FROM));
    for (const r of items) {
      if (r.start >= now.minutes) expect(["done", "noshow"]).not.toContain(r.state);
    }
  });
});

describe("Reservas through the example API", () => {
  it("reads the configuration back as the example's", async () => {
    const [wire, direct] = await run(Promise.all([httpSource().config(), createDemo("services", null, { clock: "business" }).config()]));
    expect(wire).toMatchObject(direct);
    expect(wire.services?.catalog.length).toBeGreaterThan(0);
    // What the example may not keep reads as the API's defaults.
    expect(wire.agent?.minNoticeMin ?? 60).toBe(direct.agent?.minNoticeMin ?? 60);
    expect(wire.reminders ?? true).toBe(direct.reminders ?? true);
  });

  it("reads a week of bookings back the same; Lucía is the Bandeja's", async () => {
    const http = httpSource();
    await run(http.config());
    const [wire, direct] = await run(Promise.all([http.range(FROM, TO), createDemo("services", null, { clock: "business" }).range(FROM, TO)]));
    expect(wire.items.length).toBeGreaterThan(20);
    const lucia = wire.items.find((r) => r.customer.name === "Lucía Fernández");
    expect(lucia?.customer).toEqual({ name: "Lucía Fernández", phone: "+34 600 000 001", conversationId: demoIds.lucia });
    const others = (items: Reservation[]) => items.filter((r) => r.customer.name !== "Lucía Fernández").map(listed);
    expect(others(wire.items)).toMatchObject(others(direct.items));
    // Only made-up numbers leave the example API.
    for (const r of wire.items) if (r.customer.phone) expect(r.customer.phone).toMatch(MADE_UP);
  });

  it("reads one booking with its history, the waitlist and the free slots back the same", async () => {
    const http = httpSource();
    const direct = createDemo("services", null, { clock: "business" });
    await run(http.config());
    const { items } = await run(direct.range(FROM, FROM));
    await run(http.range(FROM, FROM));
    const one = items.find((r) => r.events.length > 1) ?? items[0];
    expect(one).toBeDefined();
    const [a, b] = await run(Promise.all([http.booking(one!.id), direct.booking(one!.id)]));
    expect(a.events.length).toBeGreaterThan(1);
    expect(plain(a)).toMatchObject(plain(b));

    const [wa, wd] = await run(Promise.all([http.waitlist(), direct.waitlist()]));
    expect(wa.map(waited)).toMatchObject(wd.map(waited));
    for (const w of wa) if (w.phone) expect(w.phone).toMatch(MADE_UP);

    const c = await run(direct.config());
    const service = c.services?.catalog[0]?.id;
    const [sa, sd] = await run(Promise.all([http.freeSlots({ date: "2026-11-18", serviceId: service }), direct.freeSlots({ date: "2026-11-18", serviceId: service })]));
    expect(sa.length).toBeGreaterThan(0);
    expect(sa).toEqual(sd);
  });

  it("acts, creates and changes settings through the wire, with the API's refusals", async () => {
    const http = httpSource();
    await run(http.config());
    const { items } = await run(http.range(FROM, TO));
    const pending = items.find((r) => r.actions.includes("confirm"));
    expect(pending).toBeDefined();
    const confirmed = await run(http.act(pending!, "confirm"));
    expect(confirmed.state).toBe("confirmed");
    expect(confirmed.version).toBe(pending!.version + 1);
    // The same version again is stale (412), as the API says it.
    await expect(run(http.act(pending!, "cancel"))).rejects.toMatchObject({ status: 412, code: "stale" });

    const c = await run(http.config());
    const service = c.services!.catalog[0]!;
    const slot = (await run(http.freeSlots({ date: "2026-11-18", serviceId: service.id })))[0]!;
    const made = await run(
      http.create({ date: "2026-11-18", time: slot.time, customer: { name: "Irene Prueba", phone: "+34 600 000 099" }, serviceId: service.id, proId: slot.pro?.id ?? null }, "key-1"),
    );
    // A number typed in comes back as it was typed.
    expect(made).toMatchObject({ date: "2026-11-18", start: slot.time, state: "confirmed", origin: "person", customer: { name: "Irene Prueba", phone: "+34 600 000 099" } });
    expect((await run(http.range("2026-11-18", "2026-11-18"))).items.some((r) => r.id === made.id)).toBe(true);

    const patched = await run(http.patchConfig({ waitlist: { enabled: false }, reminders: false, agent: { minNoticeMin: 120 } }, c.version));
    expect(patched.waitlist.enabled).toBe(false);
    expect(patched.version).toBe(c.version + 1);
    // Spec 069 R17.1: the agent's notice and the reminder read back as saved.
    expect(patched.reminders).toBe(false);
    expect(patched.agent?.minNoticeMin).toBe(120);

    const err = await run(http.act({ id: "does-not-exist", version: 1 }, "confirm")).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "not_found" });
  });

  it("gives the Bandeja's contact sheet Lucía's next reservation", async () => {
    const { demoFetch } = jest.requireActual("@/api/demo") as typeof import("@/api/demo");
    const res = await run(demoFetch(`http://demo.test/console/lite/inbox/conversations/${demoIds.lucia}`));
    const body = (await res.json()) as { contact: { next_booking: { status: string; service_name: string | null; local: { date: string } } | null } };
    expect(body.contact.next_booking).toMatchObject({ status: "confirmed", service_name: "Corte y peinado", local: { date: "2026-11-18" } });
  });
});
