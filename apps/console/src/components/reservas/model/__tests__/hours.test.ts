import { describe, expect, it } from "vitest";

import { dayValid, emptyWeek, rangesLabel, sameWeek, scheduleValid, timeOptions, weekInvalidDays } from "../hours";
import { weekHours } from "./fixtures";

/** Spec 043 (T025): the hours editors validate as the API does, before saving. */
describe("hours", () => {
  it("offers the half hours of the day", () => {
    const opts = timeOptions();
    expect(opts[0]).toBe("05:00");
    expect(opts[opts.length - 1]).toBe("23:30");
    expect(opts).toContain("13:30");
  });

  it("a day has up to two ranges, in order, each closing after it opens", () => {
    expect(dayValid([])).toBe(true);
    expect(dayValid([{ from: "09:00", to: "14:00" }, { from: "15:00", to: "19:00" }])).toBe(true);
    expect(dayValid([{ from: "14:00", to: "09:00" }])).toBe(false);
    expect(dayValid([{ from: "09:00", to: "14:00" }, { from: "13:00", to: "19:00" }])).toBe(false);
    expect(weekInvalidDays({ ...emptyWeek(), friday: [{ from: "10:00", to: "10:00" }] })).toEqual(["friday"]);
  });

  it("reads the ranges and compares weeks", () => {
    expect(rangesLabel([{ from: "09:00", to: "14:00" }, { from: "15:00", to: "19:00" }])).toBe("09:00 – 14:00 · 15:00 – 19:00");
    expect(rangesLabel([])).toBeNull();
    expect(sameWeek(weekHours(), weekHours())).toBe(true);
    expect(sameWeek(weekHours(), weekHours({ sunday: [{ from: "10:00", to: "12:00" }] }))).toBe(false);
  });

  it("booking hours of Aforo: shifts apart, a step that divides them", () => {
    const ok = { model: "shifts" as const, step_minutes: 30, shifts: [{ name: "Comida", from: "13:00", to: "15:00" }, { name: "Cena", from: "20:00", to: "22:00" }] };
    expect(scheduleValid(ok)).toBe(true);
    expect(scheduleValid({ ...ok, step_minutes: 45 })).toBe(false);
    expect(scheduleValid({ ...ok, step_minutes: 90 })).toBe(false);
    expect(scheduleValid({ ...ok, shifts: [{ name: "A", from: "13:00", to: "15:00" }, { name: "B", from: "14:00", to: "16:00" }] })).toBe(false);
    expect(scheduleValid({ ...ok, shifts: [] })).toBe(false);
    expect(scheduleValid({ ...ok, shifts: [{ name: " ", from: "13:00", to: "15:00" }] })).toBe(false);
    expect(scheduleValid({ model: "slots", step_minutes: 60, from: "12:00", to: "23:00" })).toBe(true);
    expect(scheduleValid({ model: "slots", step_minutes: 120, from: "12:00", to: "23:00" })).toBe(false);
  });
});
