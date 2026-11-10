import { describe, expect, it } from "vitest";

import {
  addDays,
  dayLabel,
  daysBetween,
  formatMinutes,
  fromMinutes,
  isDay,
  localClock,
  monthWeeks,
  periodLabel,
  periodRange,
  relativeDay,
  shiftPeriod,
  shortDay,
  toMinutes,
  weekdayOf,
} from "../dates";
import { parseReservasUrl, reservasHref } from "../url-state";

const WORDS = { today: "Hoy", tomorrow: "Mañana", yesterday: "Ayer" };

/** Spec 043 (T022): days are local `YYYY-MM-DD`, weeks start on Monday, the period has its own control. */
describe("dates of Reservas", () => {
  it("knows a real day from a string that looks like one", () => {
    expect(isDay("2026-10-22")).toBe(true);
    expect(isDay("2026-02-30")).toBe(false);
    expect(isDay("22/10/2026")).toBe(false);
    expect(isDay(undefined)).toBe(false);
  });

  it("walks days across months and years without a time zone moving them", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(daysBetween("2026-10-30", "2026-11-02")).toEqual(["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"]);
    expect(weekdayOf("2026-10-22")).toBe("thursday");
  });

  it("a period is a day, a Monday-to-Sunday week, or a month", () => {
    expect(periodRange("day", "2026-10-22")).toEqual({ from: "2026-10-22", to: "2026-10-22" });
    expect(periodRange("week", "2026-10-22")).toEqual({ from: "2026-10-19", to: "2026-10-25" });
    expect(periodRange("week", "2026-10-19")).toEqual({ from: "2026-10-19", to: "2026-10-25" });
    expect(periodRange("month", "2026-02-14")).toEqual({ from: "2026-02-01", to: "2026-02-28" });
  });

  it("‹ › move one day, one week, or to the first of the next month", () => {
    expect(shiftPeriod("day", "2026-10-22", 1)).toBe("2026-10-23");
    expect(shiftPeriod("week", "2026-10-22", -1)).toBe("2026-10-15");
    expect(shiftPeriod("month", "2026-01-31", 1)).toBe("2026-02-01");
    expect(shiftPeriod("month", "2026-01-31", -1)).toBe("2025-12-01");
  });

  it("a month calendar is whole Monday-first weeks", () => {
    const weeks = monthWeeks("2026-10-22");
    expect(weeks[0]![0]).toBe("2026-09-28");
    expect(weeks[weeks.length - 1]![6]).toBe("2026-11-01");
    expect(weeks.every((w) => w.length === 7)).toBe(true);
  });

  it("hours are minutes since midnight, and durations read like the design", () => {
    expect(toMinutes("16:30")).toBe(990);
    expect(fromMinutes(990)).toBe("16:30");
    expect(fromMinutes(1440)).toBe("00:00");
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(60)).toBe("1 h");
    expect(formatMinutes(90)).toBe("1 h 30 min");
  });

  it("today and now are the business's, not the browser's", () => {
    // 02:30 UTC on the 23rd is still the 22nd, 23:30, in Santiago (UTC−3).
    expect(localClock(new Date("2026-10-23T02:30:00Z"), "America/Santiago")).toEqual({ date: "2026-10-22", minutes: 23 * 60 + 30 });
    expect(localClock(new Date("2026-10-23T02:30:00Z"), "Not/AZone")).toEqual({ date: "2026-10-23", minutes: 150 });
  });

  it("says the period in words, in both languages", () => {
    expect(dayLabel("2026-10-06", "es")).toBe("martes, 6 de octubre");
    expect(periodLabel("day", "2026-10-06", "es")).toBe("Martes, 6 de octubre");
    expect(periodLabel("month", "2026-10-06", "es")).toBe("Octubre de 2026");
    expect(periodLabel("month", "2026-10-06", "en")).toBe("October 2026");
    expect(periodLabel("week", "2026-10-06", "es")).toMatch(/5\s*–\s*11 de octubre/);
    expect(shortDay("2026-10-07", "es")).toBe("Mié 7");
    expect(shortDay("2026-10-07", "en")).toBe("Wed 7");
    expect(relativeDay("2026-10-22", "2026-10-22", "es", WORDS)).toBe("Hoy");
    expect(relativeDay("2026-10-23", "2026-10-22", "es", WORDS)).toBe("Mañana");
    expect(relativeDay("2026-10-24", "2026-10-22", "es", WORDS)).toBe("Sáb 24");
  });
});

describe("the URL holds the screen's state", () => {
  const ctx = { today: "2026-10-22", mode: "services" as const };

  it("defaults: Agenda, grid, today; Servicios by day and Aforo by week", () => {
    expect(parseReservasUrl({}, ctx)).toEqual({ tab: "agenda", view: "grid", period: "day", date: "2026-10-22", staff: null });
    expect(parseReservasUrl({}, { ...ctx, mode: "capacity" }).period).toBe("week");
  });

  it("ignores what it does not understand instead of failing", () => {
    const s = parseReservasUrl({ tab: "x", view: "table", period: "year", date: "2026-02-30", staff: "lucia" }, ctx);
    expect(s).toEqual({ tab: "agenda", view: "grid", period: "day", date: "2026-10-22", staff: null });
    expect(parseReservasUrl({ date: "9999-01-01" }, ctx).date).toBe("2026-10-22");
  });

  it("writes only what differs from the default, and keeps the day across tabs", () => {
    const s = parseReservasUrl({}, ctx);
    expect(reservasHref(s, {}, ctx)).toBe("/reservas");
    expect(reservasHref(s, { view: "list", period: "week", date: "2026-10-23" }, ctx)).toBe(
      "/reservas?view=list&period=week&date=2026-10-23",
    );
    const onDay = { ...s, date: "2026-10-23" };
    expect(reservasHref(onDay, { tab: "settings" }, ctx)).toBe("/reservas?tab=settings&date=2026-10-23");
  });
});

describe("open days for the day chips", () => {
  it("skips the days the business does not open and keeps a prefilled day", async () => {
    const { openDays, weekdayOf } = await import("../dates");
    const noSundays = (d: string) => weekdayOf(d) !== "sunday";
    expect(openDays("2026-10-24", 3, noSundays)).toEqual(["2026-10-24", "2026-10-26", "2026-10-27"]);
    expect(openDays("2026-10-24", 2, noSundays, "2026-11-20")).toEqual(["2026-10-24", "2026-10-26", "2026-11-20"]);
    expect(openDays("2026-10-24", 2, noSundays, "2026-10-01")).toEqual(["2026-10-24", "2026-10-26"]);
    expect(openDays("2026-10-24", 2, () => false)).toEqual([]);
  });
});
