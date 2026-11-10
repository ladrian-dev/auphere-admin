import {
  addDays,
  arrivingNextHour,
  currentSlot,
  daySummary,
  hhmm,
  insideAt,
  isClosed,
  isPast,
  lateBy,
  monthGrid,
  nowFrom,
  occupancyLevel,
  parseHHMM,
  runsOutOn,
  slotsOfDay,
  sinceMinutes,
  upcoming,
  wallClock,
  weekStart,
  weekday,
} from "@/lib/reservas-model";
import type { ResConfig, Reservation } from "@/api/reservas";

/**
 * Spec 044, data-model.md: what the phone works out by itself about a day of
 * reservations, always in the business's own wall time (research D3).
 */

const res = (over: Partial<Reservation>): Reservation => ({
  id: "r",
  date: "2026-10-22",
  start: 13 * 60,
  end: 14 * 60 + 30,
  state: "confirmed",
  customer: { name: "Camila Rojas", phone: null },
  origin: "agent",
  channel: "whatsapp",
  by: null,
  createdAt: "2026-10-21T10:00:00-03:00",
  arrivedAt: null,
  service: null,
  pro: null,
  partySize: 4,
  conflict: null,
  events: [],
  actions: [],
  version: 1,
  arrivedLocal: null,
  lateMinutes: null,
  ...over,
});

const capacityConfig: ResConfig = {
  mode: "capacity",
  timezone: "America/Santiago",
  currency: "CLP",
  hours: [1, 2, 3, 4, 5, 6, 7].map((weekday) => ({ weekday: weekday as 1, open: 13 * 60, close: 23 * 60 })),
  hoursLabel: null,
  hoursMissing: false,
  version: 1,
  waitlist: { enabled: true, leadHours: 2, editable: true },
  confirmation: { enabled: true, when: "24h", editable: true },
  services: null,
  capacity: {
    unit: "comensales",
    capacity: 64,
    stayMin: 90,
    maxParty: 10,
    walkinReserved: 6,
    shifts: [
      { name: "Comida", from: 13 * 60, to: 15 * 60, everyMin: 30 },
      { name: "Cena", from: 20 * 60, to: 22 * 60, everyMin: 30 },
    ],
    closed: [{ weekday: 7, shift: "Cena" }],
    blocks: [],
    editable: true,
  },
};

describe("time in the business's wall clock", () => {
  it("reads and writes HH:MM", () => {
    expect(parseHHMM("09:05")).toBe(545);
    expect(hhmm(545)).toBe("09:05");
    expect(hhmm(20 * 60)).toBe("20:00");
  });

  it("moves dates by days, across months, and knows Monday is 1", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-10-01", -1)).toBe("2026-09-30");
    expect(weekday("2026-10-19")).toBe(1);
    expect(weekday("2026-10-25")).toBe(7);
    expect(weekStart("2026-10-22")).toBe("2026-10-19");
  });

  it("takes «now» from the server's time and moves it with the phone's clock", () => {
    const now = nowFrom("2026-10-22T11:20:00-03:00", 1_000_000);
    expect(now.date).toBe("2026-10-22");
    expect(now.minutes).toBe(11 * 60 + 20);
    expect(sinceMinutes(now, 1_000_000 + 10 * 60_000)).toEqual({ date: "2026-10-22", minutes: 11 * 60 + 30 });
    // Past midnight the date moves too.
    const late = nowFrom("2026-10-22T23:50:00-03:00", 0);
    expect(sinceMinutes(late, 20 * 60_000)).toEqual({ date: "2026-10-23", minutes: 10 });
  });

  it("reads a wall clock in a time zone, not the phone's", () => {
    // 15:20 UTC is 12:20 in Santiago on 2026-10-22 (UTC−3).
    expect(wallClock("America/Santiago", new Date("2026-10-22T15:20:00Z"))).toEqual({ date: "2026-10-22", minutes: 12 * 60 + 20 });
  });
});

describe("a day", () => {
  it("is closed when the business hours have no entry for its weekday", () => {
    const services: ResConfig = { ...capacityConfig, mode: "services", capacity: null, hours: [{ weekday: 1, open: 540, close: 1140 }] };
    expect(isClosed(services, "2026-10-19")).toBe(false);
    expect(isClosed(services, "2026-10-25")).toBe(true);
  });

  it("in Aforo is closed when every shift of that weekday is closed", () => {
    expect(isClosed(capacityConfig, "2026-10-25")).toBe(false); // Sunday lunch still open
    expect(slotsOfDay(capacityConfig, "2026-10-25").map((s) => s.time)).toEqual([780, 810, 840, 870, 900]);
    expect(slotsOfDay(capacityConfig, "2026-10-22")).toHaveLength(10);
  });

  it("counts the day without the cancelled ones", () => {
    const items = [res({ state: "pending" }), res({ state: "confirmed" }), res({ state: "cancelled" }), res({ state: "pending" })];
    expect(daySummary(items)).toEqual({ total: 3, unconfirmed: 2 });
  });

  it("dims what already ended", () => {
    const now = { date: "2026-10-22", minutes: 15 * 60 };
    expect(isPast(res({ end: 14 * 60 }), now)).toBe(true);
    expect(isPast(res({ end: 16 * 60 }), now)).toBe(false);
    expect(isPast(res({ date: "2026-10-21", end: 23 * 60 }), now)).toBe(true);
  });
});

describe("Aforo", () => {
  it("counts who is inside at a time: arrived within the stay, never the cancelled or no-shows", () => {
    const items = [
      res({ start: 13 * 60, partySize: 4 }),
      res({ start: 13 * 60 + 30, partySize: 2 }),
      res({ start: 12 * 60, partySize: 6 }), // left at 13:30
      res({ start: 13 * 60, partySize: 8, state: "cancelled" }),
      res({ start: 13 * 60, partySize: 3, state: "noshow" }),
    ];
    expect(insideAt(items, "2026-10-22", 13 * 60 + 45, 90)).toBe(6);
    expect(insideAt(items, "2026-10-22", 13 * 60 + 15, 90)).toBe(10);
  });

  it("is late from 15 minutes past its time, while it still could be inside", () => {
    const now = { date: "2026-10-22", minutes: 13 * 60 + 20 };
    expect(lateBy(res({ start: 13 * 60 }), now, 90)).toBe(20);
    expect(lateBy(res({ start: 13 * 60 + 10 }), now, 90)).toBeNull();
    expect(lateBy(res({ start: 13 * 60, state: "arrived" }), now, 90)).toBeNull();
    expect(lateBy(res({ start: 11 * 60 }), now, 90)).toBeNull();
  });

  it("adds who arrives in the next hour", () => {
    const now = { date: "2026-10-22", minutes: 13 * 60 + 20 };
    const items = [res({ start: 13 * 60 + 30, partySize: 4 }), res({ start: 14 * 60, partySize: 2 }), res({ start: 14 * 60 + 30, partySize: 6 }), res({ start: 13 * 60 + 30, partySize: 5, state: "cancelled" })];
    expect(arrivingNextHour(items, now)).toBe(6);
  });

  it("knows the slot under way, and that there is none outside the shifts", () => {
    expect(currentSlot(capacityConfig, "2026-10-22", 13 * 60 + 20)).toBe(13 * 60);
    // The last arrival time holds until its interval ends: 15:00 until 15:30, then no service.
    expect(currentSlot(capacityConfig, "2026-10-22", 15 * 60 + 20)).toBe(15 * 60);
    expect(currentSlot(capacityConfig, "2026-10-22", 15 * 60 + 40)).toBeNull();
    expect(currentSlot(capacityConfig, "2026-10-22", 17 * 60)).toBeNull();
  });

  it("grades occupancy in five steps and says full", () => {
    expect(occupancyLevel(10, 64)).toBe(0);
    expect(occupancyLevel(30, 64)).toBe(1);
    expect(occupancyLevel(45, 64)).toBe(2);
    expect(occupancyLevel(60, 64)).toBe(3);
    expect(occupancyLevel(64, 64)).toBe("full");
  });
});

describe("the next ones of today", () => {
  it("lists the open ones from now on, three at most", () => {
    const now = { date: "2026-10-22", minutes: 11 * 60 + 20 };
    const items = [
      res({ id: "a", start: 10 * 60 }),
      res({ id: "b", start: 11 * 60 + 30 }),
      res({ id: "c", start: 12 * 60, state: "cancelled" }),
      res({ id: "d", start: 12 * 60 + 30 }),
      res({ id: "e", start: 15 * 60 }),
      res({ id: "f", start: 16 * 60 }),
    ];
    expect(upcoming(items, now).map((r) => r.id)).toEqual(["b", "d", "e"]);
  });
});

describe("the month", () => {
  it("is weeks from Monday, with the days of other months empty", () => {
    const grid = monthGrid("2026-10-15");
    expect(grid[0]).toEqual([null, null, null, "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
    expect(grid.at(-1)?.filter(Boolean).at(-1)).toBe("2026-10-31");
    expect(grid.every((w) => w.length === 7)).toBe(true);
  });
});

describe("how long the balance lasts (R13.1)", () => {
  it("is today plus the whole days left", () => {
    expect(runsOutOn(11.7, "2026-10-06")).toBe("2026-10-17");
    expect(runsOutOn(null, "2026-10-06")).toBeNull();
  });
});
