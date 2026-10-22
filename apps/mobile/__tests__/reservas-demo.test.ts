import { demoModeOf, demoStateOf } from "@/config";
import { createDemo } from "@/api/reservas-demo";
import { ApiError } from "@/api/errors";
import { addDays, sinceMinutes } from "@/lib/reservas-model";

/**
 * Spec 044, Requisito 18 and research D2: example data for Reservas, only in a
 * development build that asks for it — and while it exists, it follows the
 * API's rules the screens depend on.
 */
describe("only in development (R18.1, R18.2)", () => {
  it("is off outside a development build, whatever the environment says", () => {
    expect(demoModeOf("services", false)).toBeNull();
    expect(demoModeOf("capacity", false)).toBeNull();
    expect(demoStateOf("error", false)).toBeNull();
  });

  it("is on in development only for a mode it knows", () => {
    expect(demoModeOf("services", true)).toBe("services");
    expect(demoModeOf("capacity", true)).toBe("capacity");
    expect(demoModeOf("tables", true)).toBeNull();
    expect(demoModeOf(undefined, true)).toBeNull();
  });
});

jest.useFakeTimers({ doNotFake: ["Date"] });
/** Let the example's latency pass; the outcome is caught first so a refusal is never «unhandled». */
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

describe("the example source", () => {
  it("adds Reservas to the client's modules, before Consumo", () => {
    const demo = createDemo("services", null);
    const me = demo.me({ nav: ["panel", "inbox", "usage"], client: { modules: ["panel", "inbox", "usage"], name: "x" } });
    expect(me.nav).toEqual(["panel", "inbox", "reservas", "usage"]);
    expect(me.client.modules).toContain("reservas");
  });

  it("offers only the actions the API would allow now", async () => {
    const demo = createDemo("services", null);
    const today = sinceMinutes((await run(demo.range("2026-01-01", "2026-01-01"))).now);
    const { items } = await run(demo.range(today.date, addDays(today.date, 1)));
    expect(items.length).toBeGreaterThan(0);
    for (const r of items) {
      if (r.actions.includes("cancel")) expect(r.state === "pending" || r.state === "confirmed").toBe(true);
      if (r.actions.includes("confirm")) expect(r.state).toBe("pending");
      if (r.state === "cancelled" || r.state === "done") expect(r.actions).toEqual([]);
      if (r.actions.includes("noshow")) expect(r.start).toBeLessThanOrEqual(today.minutes);
    }
  });

  it("never tells a history that goes back in time (first iOS pass: asked to confirm before it existed)", async () => {
    const demo = createDemo("services", null);
    const today = sinceMinutes((await run(demo.range("2026-01-01", "2026-01-01"))).now);
    const { items } = await run(demo.range(addDays(today.date, -3), addDays(today.date, 7)));
    for (const r of items) {
      const times = r.events.map((e) => Date.parse(e.at));
      expect(times).toEqual([...times].sort((a, b) => a - b));
    }
  });

  it("refuses a slot that is no longer free, and answers the same key once", async () => {
    const demo = createDemo("services", null);
    const now = sinceMinutes((await run(demo.range("2026-01-01", "2026-01-01"))).now);
    const tomorrow = addDays(now.date, 1);
    const slots = await run(demo.freeSlots({ date: tomorrow, serviceId: "s-corte" }));
    const first = slots[0]!;
    const body = { date: tomorrow, time: first.time, customer: { name: "Lucía Fernández", phone: null }, serviceId: "s-corte", proId: first.pro?.id ?? null };
    const a = await run(demo.create(body, "k1"));
    const again = await run(demo.create(body, "k1"));
    expect(again.id).toBe(a.id);
    await expect(run(demo.create(body, "k2"))).rejects.toMatchObject({ code: "slot_taken" });
  });

  it("in Aforo, a walk-in that does not fit is «no_room»", async () => {
    const demo = createDemo("capacity", null);
    await expect(run(demo.walkIn({ partySize: 200, name: null }, "w1"))).rejects.toBeInstanceOf(ApiError);
    await expect(run(demo.walkIn({ partySize: 200, name: null }, "w2"))).rejects.toMatchObject({ code: "no_room" });
    const ok = await run(demo.walkIn({ partySize: 2, name: null }, "w3"));
    // The API keeps no name (043 §4); the screen says «Sin nombre».
    expect(ok).toMatchObject({ state: "arrived", origin: "walkin", channel: "in_person", customer: { name: "" } });
  });

  it("can be forced empty or failing, to see those states", async () => {
    const empty = createDemo("capacity", "empty");
    const now = sinceMinutes((await run(empty.range("2026-01-01", "2026-01-01"))).now);
    expect((await run(empty.range(now.date, now.date))).items).toEqual([]);
    const failing = createDemo("services", "error");
    await expect(run(failing.config())).rejects.toBeInstanceOf(ApiError);
  });
});
