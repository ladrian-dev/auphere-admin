import { WEEKDAYS, type CapacitySchedule, type TimeRange, type WeekHours } from "@/lib/backend/reservas";

import { fromMinutes, toMinutes } from "./dates";

/**
 * Editing hours (spec 043, T025): the business's week, a person's week, and
 * Aforo's booking hours. Validation here mirrors the API's so the person is
 * told before saving; the API stays the judge (422).
 */

/** Every `step` minutes of the day, from 05:00 to 23:30 by default: the choices of a from–to. */
export function timeOptions(step = 30, from = 5 * 60, to = 23 * 60 + 30): string[] {
  const out: string[] = [];
  for (let m = from; m <= to; m += step) out.push(fromMinutes(m));
  return out;
}

/** Up to two ranges, each closing after it opens, the second after the first. */
export function dayValid(ranges: readonly TimeRange[]): boolean {
  if (ranges.length > 2) return false;
  if (ranges.some((r) => r.from >= r.to)) return false;
  return ranges.length < 2 || ranges[0]!.to <= ranges[1]!.from;
}

export function weekInvalidDays(week: WeekHours): (typeof WEEKDAYS)[number][] {
  return WEEKDAYS.filter((d) => !dayValid(week[d]));
}

export function emptyWeek(): WeekHours {
  return { monday: [], tuesday: [], wednesday: [], thursday: [], friday: [], saturday: [], sunday: [] };
}

/** «09:00 – 14:00 · 15:00 – 19:00», or `null` when closed. */
export function rangesLabel(ranges: readonly TimeRange[]): string | null {
  return ranges.length ? ranges.map((r) => `${r.from} – ${r.to}`).join(" · ") : null;
}

/** Same hours as the business, day by day (a person's «Horario del negocio»). */
export function sameWeek(a: WeekHours, b: WeekHours): boolean {
  return WEEKDAYS.every((d) => JSON.stringify(a[d]) === JSON.stringify(b[d]));
}

/**
 * Aforo's booking hours (contract §2): shifts that do not overlap, 1 to 6,
 * each starting before it ends, and a step that divides each one; or slots
 * from–to (the last arrival included) that the step divides.
 */
export function scheduleValid(s: CapacitySchedule): boolean {
  const divides = (from: string, to: string) => (toMinutes(to) - toMinutes(from)) % s.step_minutes === 0;
  if (![15, 30, 60, 90, 120].includes(s.step_minutes)) return false;
  if (s.model === "slots") return s.from < s.to && divides(s.from, s.to);
  if (s.shifts.length < 1 || s.shifts.length > 6) return false;
  const sorted = [...s.shifts].sort((a, b) => a.from.localeCompare(b.from));
  return sorted.every(
    (sh, i) => sh.name.trim() !== "" && sh.from < sh.to && divides(sh.from, sh.to) && (i === 0 || sorted[i - 1]!.to < sh.from),
  );
}
